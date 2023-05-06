from datetime import date
from datetime import datetime
import pandas as pd
import numpy as np

def tidy_raw_df(df):
    """
    Tidies the raw DataFrame by filtering out irrelevant columns, replacing synonym languages,
    adding a column of 1s to sum for open_repos, and renaming columns.

    Parameters:
    df (pandas.DataFrame): The raw DataFrame to be tidied.

    Returns:
    pandas.DataFrame: The tidied DataFrame.
    """
    # Drop columns that are not needed
    columns_to_drop = ['node_id', 'url', 'forks_url', 'keys_url', 'collaborators_url', 'teams_url',
                       'hooks_url', 'issue_events_url', 'events_url', 'assignees_url', 'branches_url',
                       'tags_url', 'blobs_url', 'git_tags_url', 'git_refs_url', 'trees_url',
                       'statuses_url', 'languages_url', 'stargazers_url', 'contributors_url', 'subscribers_url',
                       'subscription_url', 'commits_url', 'git_commits_url', 'comments_url', 'issue_comment_url',
                       'contents_url', 'compare_url', 'merges_url', 'archive_url', 'downloads_url', 'issues_url',
                       'pulls_url', 'milestones_url', 'notifications_url', 'labels_url', 'releases_url',
                       'deployments_url', 'git_url', 'ssh_url', 'clone_url', 'svn_url',
                       'mirror_url', 'permissions']

    existing_columns = set(df.columns)
    columns_to_drop = list(filter(lambda col: col in existing_columns, columns_to_drop))

    filtered_df = df.drop(columns=columns_to_drop)

    # Replace synonym languages
    filtered_df['language'] = filtered_df['language'].str.replace('Jupyter Notebook', 'Python', regex=True) \
                                                     .str.replace('SCSS|CSS', 'HTML', regex=True)

    # Add a column of 1s to sum for open_repos
    filtered_df = filtered_df.assign(open_repo_count=1)

    # Rename columns
    column_mapper = {col_name: col_name.replace('.', '_') for col_name in filtered_df.columns}
    filtered_df = filtered_df.rename(columns=column_mapper)

    return filtered_df

def aggregate_org_raw(df):
    """Aggregate the raw data by organization and date.

    Args:
        df (pandas.DataFrame): The raw data containing the repositories information.

    Returns:
        pandas.DataFrame: The aggregated data by organization and date, containing the cumulative sum of open
        repositories per day.
    """
    # Convert created_at column to date type (day only)
    df['created_at'] = pd.to_datetime(df['created_at']).apply(lambda x: x.strftime("%Y-%m-%d"))

    # Group by organization and created_at columns, and calculate the cumulative sum of the numerical columns
    # (open_repo_count and size)
    aggregate_df = (df.groupby(['owner_login', 'created_at'])
                    .agg({'open_repo_count': 'sum', 'size': 'sum'})
                    .groupby(level=[0])
                    .cumsum()
                    .reset_index())

    # Return the relevant columns (owner_login, created_at, and open_repo_count)
    return aggregate_df[['owner_login', 'created_at', 'open_repo_count']]

def create_top_column_df(df, column):
    """Create a dataframe showing the top value of a given column for each organization and date.

    Args:
        df (pandas.DataFrame): The input dataframe.
        column (str): The column to get the top value from.

    Returns:
        pandas.DataFrame: A dataframe containing the top value of the given column for each organization and date.
    """
    # Group by organization, created_at, and column, and get the count of each column value at each date
    df = df.groupby(['owner_login', 'created_at', column]).size()

    # Convert to a cumulative count of the column values and reset the index for the column of interest
    df = (df.groupby(level=[0, 2])
          .cumsum()
          .reset_index(level=column))

    # Pivot the dataframe to make a column for each unique column value
    df = df.pivot(columns=column).droplevel(0, axis=1)

    # Forward fill so that each column has the previous value until it increases again
    df = df.groupby(['owner_login']).ffill()

    # Convert back to long format and remove NaNs
    df = df.reset_index().melt(id_vars=['owner_login', 'created_at'], var_name=column, value_name='count').dropna()

    # Keep the row with the largest count for each organization and date
    df = (df.sort_values(by=['owner_login', 'created_at', 'count'])
          .drop_duplicates(subset=['owner_login', 'created_at'], keep='last'))

    # Drop the count column and reset the index
    df = df.drop(columns=['count']).reset_index(drop=True)

    return df

def aggregate_github_data(aggregate_df, top_license_df, top_language_df):
    """Aggregate the Github data by organization and date, and merge it with the top license and top language data.

    Args:
        aggregate_df (pandas.DataFrame): The aggregated data by organization and date, containing the cumulative sum of
        open repositories per day.
        top_license_df (pandas.DataFrame): The top license data per organization and date.
        top_language_df (pandas.DataFrame): The top language data per organization and date.

    Returns:
        pandas.DataFrame: The aggregated data merged with the top license and top language data, containing the cumulative
        sum of open repositories per day, the top license, and the top language for each organization and date.
    """
    # Merge the aggregated data with the top license and top language data, forward-filling missing values
    aggregate_df = (aggregate_df.merge(top_license_df, how='left')
                    .merge(top_language_df, how='left')
                    .apply(lambda df: df.ffill()))

    # Rename the columns to more readable names
    aggregate_df = aggregate_df.rename(columns={'owner_login': 'Organisation',
                                                'created_at': 'Date',
                                                'open_repo_count': 'Open Repositories',
                                                'license_name': 'Top License',
                                                'language': 'Top Language'
                                                })

    return aggregate_df

def fill_missing_values(df):
    """
    Fill missing values in the DataFrame and add a new row for today's date if it does not exist.
    
    :param df: DataFrame containing columns 'Organisation', 'Date', 'Open Repositories', 'Top License', 'Top Language'
    :type df: pandas.DataFrame
    :return: DataFrame with missing values filled and today's row added if necessary
    :rtype: pandas.DataFrame
    """
    def process_organization(org_df):
        """
        Process a single organization's DataFrame, filling missing values and adding today's row if necessary.
        
        :param org_df: DataFrame containing a single organization's data
        :type org_df: pandas.DataFrame
        :return: DataFrame with missing values filled and today's row added if necessary
        :rtype: pandas.DataFrame
        """
        org_df = org_df.copy()
        org_df['Date'] = pd.to_datetime(org_df['Date'])
        org_df = org_df.fillna(method='ffill')
        org_df = add_today_if_missing(org_df)
        org_df['Date'] = pd.to_datetime(org_df['Date'])
        return org_df
    
    def add_today_if_missing(org_df):
        """
        Add a new row for today's date if it does not exist in the DataFrame.
        
        :param org_df: DataFrame containing a single organization's data
        :type org_df: pandas.DataFrame
        :return: DataFrame with today's row added if necessary
        :rtype: pandas.DataFrame
        """
        last_date = org_df.iloc[-1]['Date']
        today = datetime.now().strftime('%Y-%m-%d')
        
        if today != last_date.strftime('%Y-%m-%d'):
            last_row = org_df.iloc[-1]
            new_row = create_new_row(last_row, today)
            org_df = pd.concat([org_df, pd.DataFrame([new_row])])
            
        return org_df

    def create_new_row(last_row, today):
        """
        Create a new row for today's date with the same values as the last row.
        
        :param last_row: The last row of the DataFrame
        :type last_row: pandas.Series
        :param today: Today's date as a string formatted as 'YYYY-MM-DD'
        :type today: str
        :return: Dictionary containing the new row's data
        :rtype: dict
        """
        new_row = {'Organisation': last_row['Organisation'], 'Date': today}
        for col in ['Open Repositories', 'Top License', 'Top Language']:
            new_val = last_row[col]
            new_row[col] = '' if pd.isna(new_val) else new_val
        return new_row

    orgs = set(df['Organisation'])
    processed_orgs = [process_organization(df[df['Organisation'] == org]) for org in orgs]
    result = pd.concat(processed_orgs, ignore_index=True)
    
    return result

