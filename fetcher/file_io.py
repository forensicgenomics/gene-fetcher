# This file is part of the mitoTree project and authored by Noah Hurmer.
#
# Copyright 2024, Noah Hurmer & mitoTree.
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
file_io.py

File Input/Output Utility Functions for mitoFetch

This script contains functions for managing file operations related to processed IDs,
metadata, removed IDs, and sequence files. It also includes utilities for cleaning up
old files and post-processing metadata.

Key Features:
- Save and load processed IDs, removed ids and metadata.
- Write sequences as cleaned FASTA files.
- Post-process metadata entries, including duplicate removal and version control.
- Clean up outdated files.

Dependencies: Biopython, Pandas.

Usage:
- Import functions as needed into other scripts for processing and file management.
- Ensure appropriate paths and global constants are configured in `global_defaults`.

Author: Noah Hurmer as part of the mitoTree Project.
"""


import os
from email.generator import Generator

import pandas as pd
from datetime import date, datetime
from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord

from .global_defaults import (CURRENT_PROCESSED_IDS_FILE,
                              METADATA_FILE,
                              LAST_RUN_PATH,
                              SEQS_DIR,
                              REMOVED_IDS_FILE,
                              IDS_FILE,
                              PROCESSED_IDS_DIR,
                              DEBUG_DIR,
                              TIMESTAMP)


def save_processed_ids(processed_ids, logger=None):
    """
    Save processed sequence IDs to a new processed IDs file,
    carrying over the processed IDs from the old file.

    Args:
        processed_ids (list): List of sequence IDs to save.
        logger (logging.Logger, optional): Logger for logging progress. Defaults to None.
    """
    file_path = CURRENT_PROCESSED_IDS_FILE
    old_processed_ids = load_processed_ids()

    # combine old and new IDs and write them to file
    # remove duplicates
    all_processed_ids = list(dict.fromkeys(processed_ids + old_processed_ids))

    with open(file_path, 'w') as f:
        for seq_id in all_processed_ids:
            f.write(f"{seq_id}\n")
    if logger:
        logger.info(f"Saved {len(all_processed_ids)} processed seq_ids to {file_path}. (Includes {len(old_processed_ids)} previously processed IDs.)")


def find_latest_processed_ids_file(logger=None):
    """
    Find the most recent processed IDs file in the processed IDs directory.

    Args:
        logger (logging.Logger, optional): Logger for logging progress. Defaults to None.

    Returns:
        str or None: Path to the most recent processed IDs file, or None if none exist.
    """
    try:
        files = [
            os.path.join(PROCESSED_IDS_DIR, file)
            for file in os.listdir(PROCESSED_IDS_DIR)
            if file.endswith(".txt")
        ]
        if not files:
            if logger:
                logger.warning("No processed IDs file found for soft restart.")
            return None
        latest_file = max(files, key=os.path.getctime)
        if logger:
            logger.info(f"Using the most recent processed IDs file: {latest_file}")
        return latest_file
    except Exception as e:
        if logger:
            logger.error(f"Error finding latest processed IDs file: {e}")
        return None


def load_processed_ids(logger=None):
    """
    Load processed sequence IDs from the most recent processed IDs file.

    Args:
        logger (logging.Logger, optional): Logger for logging progress. Defaults to None.

    Returns:
        list: List of processed sequence IDs.
    """
    file_path = find_latest_processed_ids_file(logger)
    if file_path:
        with open(file_path, 'r') as f:
            processed_ids = [line.strip() for line in f]
        if logger:
            logger.info(f"Loaded {len(processed_ids)} processed seq_ids from {file_path}.")
        return processed_ids
    return []


def filter_unprocessed_ids(id_list, processed_ids, logger=None):
    """
    Filter out already processed sequence IDs from the supplied list of accession numbers.

    Args:
        id_list (list): List of sequence IDs to process.
        processed_ids (list): List of already processed sequence IDs.
        logger (logging.Logger, optional): Logger for logging progress. Defaults to None.


    Returns:
        list: List of unprocessed sequence IDs.
    """
    unprocessed_ids = [seq_id for seq_id in id_list if seq_id not in processed_ids]
    if logger:
        logger.info(f"Filtered out {len(id_list) - len(unprocessed_ids)} already-processed IDs."
                    f" Remaining: {len(unprocessed_ids)}.")
    return unprocessed_ids


def save_batch_info(index, filtered_entries, removed, metas, logger=None):
    """
    Save batch information of fetched profiles.

    Args:
        index (int): Index of the current batch.
        filtered_entries (list): List of sequence IDs that passed filters.
        removed (list): List of sequence IDs that failed filters with reasons.
        metas (list): Metadata for the processed sequences.
        logger (logging.Logger, optional): Logger for logging progress. Defaults to None.
    """
    print("Saving batch info.")

    if filtered_entries:
        update_local_versions(filtered_entries, logger)
        save_metadata(metas, logger)
    if removed:
        save_removed_versions(removed, logger)

    all_processed_ids = [rem.get("accession") for rem in removed] + filtered_entries
    save_processed_ids(all_processed_ids)

    print(f"Progress saved after processing {index + 1} entries.")



def split_accession(accession):
    """
    Helper to split an accession string into ID and version.

    Args:
        accession (str): Accession string in the format 'ABC123456.1'.

    Returns:
        tuple: (accession_id, version) where version is an integer.
    """
    try:
        accession_id, version = accession.split('.')
        return accession_id, int(version)
    except ValueError:
        print(accession)
        raise ValueError(f"Invalid accession format: {accession}")


def save_metadata(new_metas, logger=None):
    """
    Save metadata to the metadata file.

    Args:
        new_metas (list or DataFrame): New metadata entries to save.
        logger (logging.Logger, optional): Logger for logging progress. Defaults to None.
    """
    meta_df = pd.DataFrame(new_metas)
    meta_df.to_csv(METADATA_FILE, mode='a', header=not os.path.exists(METADATA_FILE), index=False)
    if logger:
        logger.info(f"{len(new_metas)} metadata entries written to {METADATA_FILE}.")


def load_local_versions(logger=None):
    """
    Load local versions of sequence IDs from the local versions file.

    Args:
        logger (logging.Logger, optional): Logger for logging progress. Defaults to None.

    Returns:
        dict: Dictionary mapping accession IDs to their versions.
    """
    if not os.path.exists(IDS_FILE):
        return {}
    local_versions = {}
    with open(IDS_FILE, 'r') as f:
        for line in f:
            accession, version = line.strip().split('.')
            local_versions[accession] = int(version)
    if logger:
        logger.info(f"Loaded {len(local_versions)} local non-filtered-out versions.")
    return local_versions


def save_dropped_rows(dropped_df, reason, logger=None):
    """
    Saves dropped rows to a CSV in the debug directory, appending a 'reason' column.
    By default, it appends to a file named 'duplicates_debug.csv'.

    If you prefer a timestamped approach, you can add:
       timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
       debug_file = os.path.join(DEBUG_DIR, f"{prefix}_{timestamp}.csv")

    Args:
        dropped_df (pd.DataFrame): DataFrame of dropped rows, must have an 'accession' column.
        reason (str): Reason for dropping, e.g. "duplicate" or "update".
        logger (logging.Logger, optional): Logger for progress messages.
    """
    if dropped_df.empty:
        return

    debug_file = os.path.join(DEBUG_DIR, "duplicates_debug_" + TIMESTAMP + ".csv")

    dropped_df = dropped_df.copy()
    dropped_df["reason"] = reason

    write_header = not os.path.exists(debug_file)
    mode = 'a' if write_header is False else 'w'

    dropped_df.to_csv(debug_file, mode=mode, header=write_header, index=False)

    if logger:
        logger.info(f"Appended {len(dropped_df)} dropped rows to {debug_file} with reason '{reason}'.")


def duplicate_removal(entries, logger=None):
    """
    Remove duplicate entries based on accession and version.

    Args:
        entries (DataFrame): DataFrame of entries with accession and version columns.
        logger (logging.Logger, optional): Logger for logging progress. Defaults to None.

    Returns:
        DataFrame: Deduplicated DataFrame.
    """
    # remove identical accession+version, keeping last
    duplicates_mask = entries.duplicated(subset="accession", keep="last")
    df_duplicates = entries[duplicates_mask].copy()  # the ones to drop
    if not df_duplicates.empty:
        # save dropped accessions
        save_dropped_rows(df_duplicates, reason="duplicate", logger=logger)
        entries.drop_duplicates(subset="accession", keep="last", inplace=True)
        if logger:
            logger.warning(f"{len(df_duplicates)} duplicate entries dropped from entries.")

    # remove older version of same accession
    entries[["id", "version"]] = entries['accession'].apply(lambda x: pd.Series(split_accession(x)))
    idx_to_keep = entries.groupby("id")["version"].idxmax()
    df_older = entries.loc[~entries.index.isin(idx_to_keep)].copy()
    if not df_older.empty:
        # save dropped accessions
        save_dropped_rows(df_older, reason="update", logger=logger)
        entries = entries.loc[idx_to_keep]
        if logger:
            logger.warning(f"{len(df_older)} older versions dropped, where newer entries exist.")

    entries.drop(columns=["id", "version"], inplace=True)

    # TODO catch if we download an older version?

    return entries


def update_local_versions(entries, logger=None):
    """
    Update the local versions file with new entries, removing duplicates and older versions.

    Args:
        entries (list): List of new entries to add to the local versions file.
        logger (logging.Logger, optional): Logger for logging progress. Defaults to None.
    """
    ex_ids = []
    if os.path.exists(IDS_FILE):
        with open(IDS_FILE, 'r') as f:
            ex_ids = [line.strip() for line in f if line.strip()]

    if not len(ex_ids) and not len(entries):
        return

    ids = ex_ids + list(entries)

    ids_df = duplicate_removal(pd.DataFrame(ids, columns=["accession"]), logger=logger)
    ids_df.to_csv(IDS_FILE, index=False, header=False)

    if logger:
        logger.info(f"Updated local versions in {IDS_FILE}.")


def load_removed_versions(logger=None):
    """
    Load removed sequences from the removed ids file.

    Args:
        logger (logging.Logger, optional): Logger for logging progress. Defaults to None.

    Returns:
        dict: Dictionary mapping accession IDs to their versions.
    """
    if not os.path.exists(REMOVED_IDS_FILE):
        return []
    local_removed = {}
    with open(REMOVED_IDS_FILE, 'r') as f:
        next(f)
        for line in f:
            accession_num, _ = line.strip().split(',')
            accession, version = accession_num.strip().split('.')
            local_removed[accession] = int(version)
    if logger:
        logger.info(f"Loaded {len(local_removed)} local removed versions.")
    return local_removed


def save_removed_versions(removed_entries, logger=None):
    """
    Save removed sequences to the removed ids file.

    Args:
        removed_entries (list): List of removed entries with accession and filter reason.
        logger (logging.Logger, optional): Logger for logging progress. Defaults to None.
    """
    if not len(removed_entries):
        return

    removed_entries = pd.DataFrame(removed_entries, columns=['accession', 'filter'])
    if os.path.exists(REMOVED_IDS_FILE):
        prev_removed = pd.read_csv(REMOVED_IDS_FILE)
    else:
        prev_removed = pd.DataFrame(columns=removed_entries.columns)

    removed = pd.concat([prev_removed, removed_entries], ignore_index=True)
    removed = duplicate_removal(removed, logger=logger)

    # save back to the file
    removed.to_csv(REMOVED_IDS_FILE, index=False)
    if logger:
        logger.info(f"Saved {len(removed_entries)} entries to {REMOVED_IDS_FILE}.")


def cleanup_old_files(directory, keep_last=3, logger=None):
    """
    Cleans up old files in the specified directory, keeping only the last `keep_last` files.

    Args:
        directory (str): Path to the directory containing the files.
        keep_last (int): Number of most recent files to keep. Defaults to 3.
        logger (logging.Logger, optional): Logger for logging messages. Defaults to None.
    """
    try:
        print(f"Cleaning up files in {directory}.")
        extensions = [".txt", ".csv", ".log"]
        files = [
            os.path.join(directory, file)
            for file in os.listdir(directory) if file.endswith(tuple(extensions))
        ]
        if len(files) <= keep_last:
            if logger:
                logger.info(f"No cleanup needed for {directory}. Found {len(files)} files.")
            return

        # Sort files by their modification time, keeping the last `keep_last`
        files.sort(key=os.path.getctime, reverse=True)
        files_to_remove = files[keep_last:]

        # Remove old files
        for file in files_to_remove:
            os.remove(file)
            if logger:
                logger.info(f"Removed old file: {file}")

        if logger:
            logger.info(f"Cleanup complete for {directory}. Kept {keep_last} most recent files.")

    except Exception as e:
        if logger:
            logger.error(f"Error during cleanup of {directory}: {e}")


def write_seq_as_fasta(record, logger=None):
    """
    Cleans the sequence by replacing all 'D' with '-' and writes it to a FASTA file.

    Args:
        record (SeqRecord): A Biopython SeqRecord containing the sequence data.
        logger (logging.Logger, optional): Logger for logging errors. Defaults to None.

    Returns:
        bool: True if the operation was successful, False otherwise.
    """
    try:
        # this is a bit annoying,but in order to actually manipulate the sequence,
        # the record needs to be remade.
        # alternative would be to read the file lines as strings, not sure if thats better
        cleaned_sequence = clean_sequence(record.seq)

        cleaned_record = SeqRecord(
            Seq(cleaned_sequence),
            id=record.id,
            name=record.name,
            description=record.description
        )

        SeqIO.write(cleaned_record, f"{SEQS_DIR}/{record.id.split('.')[0]}.fasta", "fasta")

        if logger:
            logger.debug(f"FASTA for {record.id} written.")
        return True

    except Exception as e:
        if logger:
            logger.error(f"Error writing FASTA for ID {record.id}: {e}")
        else:
            print(f"Error writing FASTA for ID {record.id}: {e}")
        return False


def clean_sequence(sequence):
    """
    Clean a sequence string by defined rules.
    Currently just replacing all occurrences of 'D' with '-'.

    Args:
        sequence (str): The sequence string to clean.

    Returns:
        str: Cleaned sequence string.
    """
    return str(sequence).replace('D', '-')


def get_last_run_date(file_path=LAST_RUN_PATH, logger=None):
    """
    Reads the last run date from the specified file.

    Args:
        file_path (str): Path to the file containing the last run date.
        logger (logging.Logger, optional): Logger for writing messages. Defaults to None.

    Returns:
        datetime.date: The last run date, or None if an error occurred or the file does not exist.
    """
    try:
        # Check if the file exists
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File '{file_path}' not found.")

        # Read and process the date
        with open(file_path, 'r') as f:
            date_str = f.read().strip()

        # Convert to datetime.date
        last_run_date = datetime.strptime(date_str, "%Y-%m-%d").date()

        if logger:
            logger.info(f"Last run date fetched: {last_run_date}.")

        return last_run_date

    except Exception as e:
        message = f"Failed to read date from {file_path}: {e}"
        if logger:
            logger.error(message)
        else:
            print(message)

    return None


def write_last_run_date(file_path=LAST_RUN_PATH, run_date=None, logger=None):
    """
    Writes the given date or the current date to the specified file.

    Args:
        file_path (str): Path to the file where the date will be saved.
        run_date (datetime.date, optional): The date to save. If None, the current date is used. Defaults to None.
        logger (logging.Logger, optional): Logger for writing messages. Defaults to None.

    Returns:
        bool: True if the date was written successfully, False otherwise.
    """
    try:
        if run_date is None:
            run_date = date.today()

        run_date = run_date.strftime("%Y-%m-%d")
        with open(file_path, 'w') as f:
            f.write(run_date)

        if logger:
            logger.info(f"Date {run_date} written to {file_path}.")

        return True

    except Exception as e:
        message = f"Failed to write date to {file_path}: {e}"
        if logger:
            logger.error(message)
        else:
            print(message)

        return False


def post_process_metadata(logger=None):
    """
    Perform post-processing on the metadata file:
    - Remove duplicate accessions.
    - Keep the highest version per ID.
    - Log warnings for irregularities.
    - Save removed rows for debug purposes.

    Args:
        logger (logging.Logger, optional): Logger for logging progress. Defaults to None.
    """
    if not os.path.exists(METADATA_FILE):
        if logger:
            logger.error(f"Metadata file '{METADATA_FILE}' not found.")
        return

    meta_df = pd.read_csv(METADATA_FILE)
    if logger:
        logger.info(f"Loaded {len(meta_df) - 1} rows from metadata file.")

    print("Performing post-processing of metadata file.")
    if logger:
        logger.info(f"Performing Post-processing of metadata file.")

    # add helper columns
    meta_df['index'] = meta_df.index # order of fetched
    meta_df[['id', 'version']] = meta_df['accession'].apply(lambda x: pd.Series(split_accession(x)))

    meta_df = meta_df.sort_values(by=['id', 'version', 'index'], ascending=[True, False, True])

    # keep the highest version per group
    rows_to_keep = []
    for _, group in meta_df.groupby('id'):
        # highest version row
        best_row = group.iloc[0]
        # check if highest version is the most recent
        if best_row['index'] != group['index'].max():
            if logger:
                logger.warning(f"Highest version for ID {best_row['id']} ({best_row['accession']}) "
                               f"is not the most recently added row.\n"
                               f"Other versions present:\n"
                               f"Index  -  Accession\n"
                               f"{group['accession']}\n"
                               f"Keeping highest version anyway.")

        # check highest version row has the most filled fields
        for _, row in group.iloc[1:].iterrows():
            if row.notna().sum() > best_row.notna().sum():
                if logger:
                    logger.warning(f"Row {row['index']} with ID {row['id']} and version {row['version']} "
                                   f"has more filled fields than the highest version"
                                   f" ({best_row['accession']} @ row {best_row['index']}).")

        # split up any tied highest versions (same ID, same version) by most recently added
        max_version_rows = group[group['version'] == best_row['version']]
        best_rows = max_version_rows.loc[max_version_rows['index'] == max_version_rows['index'].max()]
        rows_to_keep.append(best_rows)

    final_df = pd.concat(rows_to_keep).drop(columns=['id', 'version', 'index']).reset_index(drop=True)
    if logger:
        logger.info(f"Removed {len(meta_df) - len(final_df)} duplicate rows.")

    # the removed rows
    removed_df = pd.concat([meta_df.drop(columns=['id', 'version', 'index']), final_df]).drop_duplicates(keep=False)

    # save cleaned metadata
    final_df.to_csv(METADATA_FILE, index=False)
    if logger:
        logger.info(f"Post-processing complete. Saved {len(final_df) - 1} rows to '{METADATA_FILE}'.")

    # write removed rows to debug file
    if len(removed_df) > 0:
        removed_file = os.path.join(DEBUG_DIR, f"removed_metadata_rows_{TIMESTAMP}.csv")
        removed_df.to_csv(removed_file, index=False)
        if logger:
            logger.info(f"Saved {len(removed_df)} removed rows to: {removed_file}")


def clean_profiles_from_data(ids_list, logger=None):
    """
    Removes any profiles (and associated data) that are NOT in the given `ids_list`.

    This function:
      1. Updates the local versions file (`IDS_FILE`) to keep only IDs that are in `ids_list`.
      2. Updates `REMOVED_IDS_FILE` (removed.csv) to keep only rows whose 'accession' is in `ids_list`.
      3. Updates `METADATA_FILE` to keep only rows whose 'accession' is in `ids_list`.
      4. Removes FASTA files from `SEQS_DIR` if their root name is not in `ids_list`.
         (For an accession like "AB123456.1", the FASTA file is "AB123456.fasta".)

    Args:
        ids_list (list): List of *full* accessions (e.g. ["AB123456.1", "XYZ789123.2"]) that should remain.
        logger (logging.Logger, optional): Logger for progress/error messages. Defaults to None.

    Returns:
        int: Returns 0 upon successful cleanup.
    """

    keep_set = set(ids_list)

    # remove from IDS_FILE
    if os.path.exists(IDS_FILE):
        try:
            with open(IDS_FILE, "r") as f:
                lines = [line.strip() for line in f if line.strip()]

            before_count = len(lines)
            kept_lines = [ln for ln in lines if ln in keep_set]
            after_count = len(kept_lines)

            if after_count < before_count:
                with open(IDS_FILE, "w") as f:
                    for ln in kept_lines:
                        f.write(ln + "\n")
                if logger:
                    logger.info(
                        f"Removed {before_count - after_count} entries from {IDS_FILE} "
                        f"that are not in the provided list."
                    )
            else:
                if logger:
                    logger.info(
                        f"No entries removed from {IDS_FILE}; all were in the provided list."
                    )
        except Exception as e:
            if logger:
                logger.error(f"Error updating {IDS_FILE}: {e}")
            else:
                print(f"Error updating {IDS_FILE}: {e}")

    # REMOVED_IDS_FILE
    if os.path.exists(REMOVED_IDS_FILE):
        try:
            df_removed = pd.read_csv(REMOVED_IDS_FILE)
            before_count = len(df_removed)
            df_removed = df_removed[df_removed["accession"].isin(keep_set)]
            after_count = len(df_removed)
            if after_count < before_count:
                df_removed.to_csv(REMOVED_IDS_FILE, index=False)
                if logger:
                    logger.info(
                        f"Removed {before_count - after_count} rows from {REMOVED_IDS_FILE} "
                        f"that are not in the provided list."
                    )
            else:
                if logger:
                    logger.info(
                        f"No rows removed from {REMOVED_IDS_FILE}; "
                        f"all were in the provided list."
                    )
        except Exception as e:
            if logger:
                logger.error(f"Error updating {REMOVED_IDS_FILE}: {e}")
            else:
                print(f"Error updating {REMOVED_IDS_FILE}: {e}")

    # METADATA_FILE
    if os.path.exists(METADATA_FILE):
        try:
            df_meta = pd.read_csv(METADATA_FILE)
            if "accession" in df_meta.columns:
                before_count = len(df_meta)
                df_meta = df_meta[df_meta["accession"].isin(keep_set)]
                after_count = len(df_meta)
                if after_count < before_count:
                    df_meta.to_csv(METADATA_FILE, index=False)
                    if logger:
                        logger.info(
                            f"Removed {before_count - after_count} rows from {METADATA_FILE} "
                            f"that are not in the provided list."
                        )
                else:
                    if logger:
                        logger.info(
                            f"No rows removed from {METADATA_FILE}; "
                            f"all were in the provided list."
                        )
            else:
                if logger:
                    logger.warning(
                        f"No 'accession' column in {METADATA_FILE}; skipping removal."
                    )
        except Exception as e:
            if logger:
                logger.error(f"Error updating {METADATA_FILE}: {e}")
            else:
                print(f"Error updating {METADATA_FILE}: {e}")

    # remove FASTA files in SEQS_DIR
    if os.path.exists(SEQS_DIR):
        try:
            valid_roots = set(acc.split(".")[0] for acc in keep_set)

            all_files = os.listdir(SEQS_DIR)
            fasta_files = [f for f in all_files if f.lower().endswith(".fasta")]

            removed_count = 0
            for fasta_name in fasta_files:
                root_name = os.path.splitext(fasta_name)[0]
                if root_name not in valid_roots:
                    # remove
                    full_path = os.path.join(SEQS_DIR, fasta_name)
                    try:
                        os.remove(full_path)
                        removed_count += 1
                        if logger:
                            logger.debug(f"Removed FASTA file not in keep list: {full_path}")
                    except Exception as e:
                        if logger:
                            logger.error(f"Error removing {full_path}: {e}")
                        else:
                            print(f"Error removing {full_path}: {e}")
            if logger and removed_count > 0:
                logger.info(
                    f"Removed {removed_count} FASTA files from {SEQS_DIR} "
                    f"that are not in the current query."
                )
        except Exception as e:
            if logger:
                logger.error(f"Error cleaning up FASTA files in {SEQS_DIR}: {e}")
            else:
                print(f"Error cleaning up FASTA files in {SEQS_DIR}: {e}")

    return 0
