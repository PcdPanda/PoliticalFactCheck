from itertools import product

import pandas as pd
import numpy as np
from scipy.signal import find_peaks
import altair as alt


class PeakDetector(object):
    df_count_columns = [
        'Name',
        'Date',
        'TweetCount',
        'SusUserCount',
        'SusDomainCount',
        'MonthTweetCount',
        'TweetPeakIQR',
        'SusUserPeakIQR',
        'SusDomainPeakIQR']

    def __init__(self, df_cand: pd.DataFrame, df_sus_users: pd.DataFrame,
                 df_new_tweets: pd.DataFrame, df_count: pd.DataFrame = None):
        self.df_sus_users = df_sus_users
        self.df_cand = df_cand
        start_date = df_new_tweets["Date"].min()
        end_date = df_new_tweets["Date"].max()
        if df_count is None:
            df_count = pd.DataFrame(columns=self.df_count_columns)
        else:
            start_date = min(start_date, df_count["Date"].min())
            end_date = max(end_date, df_count["Date"].max())
        dates = pd.date_range(str(start_date), str(
            end_date)).strftime("%Y%m%d").astype(int)
        df_index = pd.DataFrame(index=product(df_cand["Name"], dates))
        df_count = df_count.set_index(["Name", "Date"])
        df_index = df_index[~df_index.index.isin(df_count.index)]
        df_count = pd.concat([df_count, df_index])
        self.df_count = df_count.reset_index()
        self.df_count["Month"] = df_new_tweets["Date"].astype(int) // 100
        if df_new_tweets.index.name != "Id":
            df_new_tweets = df_new_tweets.set_index(["Id"])
        df_new_tweets = df_new_tweets[~df_new_tweets.index.duplicated()]
        df_new_tweets["Month"] = df_new_tweets["Date"].astype(int) // 100
        self.df_new_tweets = df_new_tweets[df_new_tweets["Name"].isin(
            df_cand["Name"])].dropna(subset=["Content"])
        self.df_sus_user_tweets = df_new_tweets[df_new_tweets["Author_id"].isin(
            df_sus_users["User_id"])]
        self.df_sus_domain_tweets = df_new_tweets[df_new_tweets["Credibility"] == 0]

    def __call__(self):
        self.add_sus_tweets_count()
        self.add_monthly_count()
        self.generate_peak()
        df_count = self.df_count
        for col in df_count.columns:
            if not col.endswith("IQR") and col != "Name":
                df_count[col] = df_count[col].astype(int)
        return df_count

    def add_sus_tweets_count(self):
        for tweet_type, df_tweets in zip(["Tweet", "SusUser", "SusDomain"], [
                                         self.df_new_tweets, self.df_sus_user_tweets, self.df_sus_domain_tweets]):
            df_tweets = self.count_tweets(df_tweets)
            self.df_count = self.df_count.set_index(["Name", "Date"])
            df_tweets = df_tweets.set_index(["Name", "Date"])
            self.df_count["Text"] = df_tweets["Text"]
            self.df_count[f"{tweet_type}Count"] = np.where(
                self.df_count["Text"].isna(),
                self.df_count[f"{tweet_type}Count"],
                self.df_count["Text"])
            self.df_count = self.df_count.reset_index().drop(["Text"], axis=1)

    def add_monthly_count(self):
        df_month_count = self.df_new_tweets.groupby(
            ["Name", "Month"]).count()["Text"]
        self.df_count = self.df_count.set_index(["Name", "Month"])
        self.df_count = self.df_count.merge(
            df_month_count, how="outer", left_index=True, right_index=True)
        self.df_count["MonthTweetCount"] = np.where(
            self.df_count["Text"].isna(),
            self.df_count["MonthTweetCount"],
            self.df_count["Text"])
        self.df_count = self.df_count.reset_index().drop(["Text"], axis=1)

    def count_tweets(self, df_tweets: pd.DataFrame):
        df_tweets = df_tweets[~df_tweets.index.duplicated()]
        df_tweets["Date"] = df_tweets["Date"].astype(int)
        df_tweets = df_tweets.groupby(["Name", "Date"])[
            "Text"].count().reset_index()
        df_tweets = df_tweets[df_tweets["Name"].isin(self.df_cand["Name"])]
        return df_tweets

    def generate_peak(self, iqrs=[1.5, 3, 4]) -> pd.DataFrame:
        df_ct_list = list()

        for name in self.df_count["Name"].drop_duplicates():
            df_cand_ct = self.df_count[self.df_count["Name"] == name].reset_index(
                drop=True)
            for count_type in ["Tweet", "SusUser", "SusDomain"]:
                for iqr in [1.5, 3, 4]:
                    for i in self.detect_peak(
                        df_cand_ct
                        [f"{count_type}Count"],
                            iqr=iqr):
                        df_cand_ct.at[i, f"{count_type}PeakIQR"] = iqr
            df_ct_list.append(df_cand_ct)
        self.df_count = pd.concat(df_ct_list).fillna(0).reset_index(drop=True)

    @staticmethod
    def detect_peak(counts: pd.Series, iqr: float = 1.5):
        if counts.empty:
            return list()
        prominence = iqr * (np.percentile(counts,
                            75) - np.percentile(counts, 25))
        peaks_indexes, _ = find_peaks(counts, prominence=prominence)
        return peaks_indexes

    @staticmethod
    def plot_peak(df_counts: pd.DataFrame, field: str):
        df_counts["Counts"] = df_counts[field] / df_counts[field].max()
        df_counts = df_counts[["Counts", "Date"]]
        df_counts["Date"] = pd.to_datetime(df_counts["Date"].astype(str))
        chart = alt.Chart(df_counts).mark_line().encode(
            y=alt.Y("Counts:Q"),
            x=alt.X("Date:T"),
            tooltip=["Counts:Q", "Date:T"]
        )
        return chart


if __name__ == "__main__":
    df_cand = pd.read_csv(
        "Data/Candidates/Candidates.csv",
        sep="\t").dropna(
        subset=["Position"])
    df_sus_users = pd.read_csv("Data/Network/NetworkUsers.csv", sep="\t")
    df_tweets = pd.read_csv("Data/Candidates/NewTweets.csv", sep="\t")
    df_count = pd.read_csv(
        "Data/Candidates/CandTweetsCount.csv",
        sep="\t").drop_duplicates(
        [
            "Name",
            "Date"]).reset_index(
                drop=True)
    pg = PeakDetector(df_cand, df_sus_users, df_tweets, df_count)
    pg.add_monthly_count()
    pg.add_sus_tweets_count()
    pg.generate_peak()
