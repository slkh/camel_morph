import os
import argparse
import gspread
import re
import json
from collections import Counter

from numpy import nan
import pandas as pd

from camel_morph.utils.utils import add_check_mark_online
from camel_morph.debugging.create_repr_lemmas_list import create_repr_lemmas_list
from camel_morph.debugging.download_sheets import download_sheets
from camel_morph.utils.utils import get_config_file

parser = argparse.ArgumentParser()
parser.add_argument("-config_file", default='config_default.json',
                        type=str, help="Config file specifying which sheets to use from `specs_sheets`.")
parser.add_argument("-config_name", default='default_config',
                    type=str, help="Name of the configuration to load from the config file.")
parser.add_argument("-mode", default='generate_lex',
                    type=str, help="Task that the script should execute.")
parser.add_argument("-download", default=False,
                    action='store_true', help="Whether or not to download the data before doing anything. This should be done in case data was changed in Google Sheets since last time this script was ran.")
parser.add_argument("-well_formedness", default=False,
                    action='store_true', help="Whether or not to perform some well-formedness checks before generating.")
parser.add_argument("-spreadsheet", default='',
                    type=str, help="Google Sheets spreadsheet name to output to.")
parser.add_argument("-sheet", default='',
                    type=str, help="Google Sheets sheet name to output to.")
parser.add_argument("-pos", default=[], nargs='+',
                    type=str, help="POS of the lemmas.")
args, _ = parser.parse_known_args([] if "__file__" not in globals() else None)

FIELDS_MAP = dict(
    lemma='LEMMA',
    form='FORM',
    cond_t='COND-T',
    cond_s='COND-S',
    gloss='GLOSS',
    line='LINE',
    pos='POS',
    gen='GEN',
    num='NUM',
    rat='RAT',
    cas='CAS',
    stem_count='STEM_COUNT'
)

COLUMNS_OUTPUT = ['LINE', 'STEM_COUNT', 'META_INFO', 'FREQ', 'LEMMA',
                  'FORM', 'COND-T', 'COND-S', 'GLOSS', 'POS', 'GEN',
                  'NUM', 'RAT', 'CAS', 'SIGNATURE', 'FLAGS']

def _strip_brackets(info):
    if info[0] == '[':
        info = info[1:]
    if info[-1] == ']':
        info = info[:-1]
    return info

def _split_field(field):
    field_split = field.split(']-[')
    for i in [0, -1]:
        field_split[i] = _strip_brackets(field_split[i])
    return field_split


def well_formedness_check(config_local):
    sheet_name = config_local['lexicon']['sheets'][0]
    dialect = config_local['dialect']
    data_path = os.path.join(
        f'data/camel-morph-{dialect}', args.config_name, f'{sheet_name}.csv')
    nom_lex = pd.read_csv(data_path)
    nom_lex = nom_lex.replace(nan, '')
    essential_columns = ['ROOT', 'LEMMA', 'FORM', 'GLOSS', 'FEAT', 'COND-T', 'COND-S']
    # Duplicate entries
    nom_lex_essential = [tuple(row) for row in nom_lex[essential_columns].values.tolist()]
    counter = Counter(nom_lex_essential)
    nom_lex_essential_set = set(nom_lex_essential)
    duplicates = Counter()
    messages = []
    if len(nom_lex_essential) != len(nom_lex_essential_set):
        for i, row in nom_lex.iterrows():
            row_ = tuple(row[essential_columns])
            if counter[row_] > 1 and duplicates[row_] < counter[row_] - 1:
                duplicates.update([row_])
                messages.append('delete-duplicate')
            else:
                messages.append('')

    # Glosses should be merged
    essential_columns_no_gloss = [col for col in essential_columns if col != 'GLOSS']
    key2indexes = {}
    for i, row in nom_lex.iterrows():
        key = tuple(row[essential_columns_no_gloss])
        key2indexes.setdefault(key, []).append(i)
    
    index2message = {}
    for key, indexes in key2indexes.items():
        for j, index in enumerate(indexes):
            if len(key2indexes[key]) > 1:
                if j:
                    index2message[index] = 'delete-merged-gloss'
                else:
                    index2message[index] = '###'.join(nom_lex.loc[index, 'GLOSS']
                                                      for index in key2indexes[key])

    messages = [(f'{messages[i]} ' if messages[i] else '') +
                (index2message[i] if i in index2message else '')
                for i in range(len(nom_lex.index))]

    if set(messages) != {''}:
        add_check_mark_online(rows=nom_lex,
                              spreadsheet=config_local['lexicon']['spreadsheet'],
                              worksheet=sheet_name,
                              status_col_name='STATUS_CHRIS',
                              write='overwrite',
                              messages=messages)


def generate_lex_rows(repr_lemmas):
    rows = {}
    for lemma_paradigm, lemmas_info in repr_lemmas.items():
        for lemma_info in lemmas_info['lemmas']:
            stem_mask = [info for info in lemma_info['meta_info'].split()
                            if 'stem' in info][0]
            stem_mask = stem_mask.split(':')[1].split('-')
            # Add all lex fields
            for field, field_header in FIELDS_MAP.items():
                values = str(lemma_info[field])
                if ']-[' in values:
                    values_ = _split_field(values)
                else:
                    values_ = [_strip_brackets(values)] * len(stem_mask)
                
                for i in range(len(stem_mask)):
                    if field not in ['gen', 'num']:
                        values_[i] = '' if values_[i] == '-' else values_[i]
                    rows.setdefault(field_header.upper(), []).append(values_[i])
            
            signature = f"{lemma_info['cond_t']} {lemma_info['gen']} {lemma_info['num']}"
            for _ in range(len(stem_mask)):
                rows.setdefault('SIGNATURE', []).append(signature)
                rows.setdefault('META_INFO', []).append(lemma_info['meta_info'])
                rows.setdefault('FREQ', []).append(lemmas_info['freq'])

            # Check for stem well-formedness, i.e., at least one stem in a lemma system
            # should match the prefix of the lemma.
            well_formed = any(True if re.match(stem, lemma_info['lemma_ar']) else False
                            for stem in _split_field(lemma_info['form_ar']))
            
            for i, stem_id in enumerate(stem_mask):
                rows.setdefault('FLAGS', []).append('check_stems' if not well_formed else '')
    
    return rows


def regenerate_signature_lex_rows(config, config_name,
                                  sheet=None, sh=None,
                                  lexicon_specs=None):
    if sheet is not None:
        sheet_df = pd.DataFrame(sheet.get_all_records())
        sheet_df['DEFINE'], sheet_df['BW'] = 'LEXICON', ''
        sheet_df['FEAT'] = ('pos:' + sheet_df['POS'] + ' gen:' + sheet_df['GEN'] +
                            ' num:' + sheet_df['NUM'] + ' rat:' + sheet_df['RAT'] +
                            ' cas:' + sheet_df['CAS'])
        lexicon_is_processed = False
    elif lexicon_specs is not None:
        sheet_df = lexicon_specs
        lexicon_is_processed = True
    else:
        raise NotImplementedError
    
    repr_lemmas = create_repr_lemmas_list(config=config,
                                          config_name=config_name,
                                          lexicon=sheet_df,
                                          lexicon_is_processed=lexicon_is_processed)

    lemma_pos2signature = {}
    for lemmas_info in repr_lemmas.values():
        for lemma_info in lemmas_info['lemmas']:
            lemma_pos = (lemma_info['lemma'], lemma_info['pos'])
            stem_mask = [info for info in lemma_info['meta_info'].split()
                            if 'stem' in info][0]
            stem_mask_str = stem_mask
            stem_mask = stem_mask.split(':')[1].split('-')
            if lemma_pos in lemma_pos2signature:
                continue
            for _ in range(len(stem_mask)):
                signature = (f"{lemma_info['cond_t']} {lemma_info['gen']} "
                            f"{lemma_info['num']} {stem_mask_str}")
                lemma_pos2signature[lemma_pos] = signature

    if sheet is None:
        return lemma_pos2signature

    signatures = []
    for _, row in sheet_df.iterrows():
        if row['POS'] in POS:
            lemma_pos = (row['LEMMA'], row['POS'])
            signatures.append(lemma_pos2signature[lemma_pos])
        else:
            signatures.append('')

    add_check_mark_online(rows=sheet_df,
                          spreadsheet=sh,
                          worksheet=sheet,
                          status_col_name='SIGNATURE',
                          write='overwrite',
                          messages=signatures)


if __name__ == "__main__":
    config = get_config_file(args.config_file)
    config_name = args.config_name
    config_local = config['local'][config_name]
    config_global = config['global']

    POS = args.pos if args.pos else config_local['pos']
    POS = POS if type(POS) is list else [POS]
    sheet_name = args.sheet if args.sheet else config_local['debugging']['sheets'][0]
    spreadsheet = args.spreadsheet if args.spreadsheet else config_local['debugging']['debugging_spreadsheet']

    data_dir = os.path.join(config_global['data_dir'],
                            f"camel-morph-{config_local['dialect']}",
                            config_name)

    sa = gspread.service_account(config_global['service_account'])

    if args.download or not os.path.exists(data_dir):
        download_sheets(config=config,
                        config_name=config_name,
                        service_account=sa)

    if args.well_formedness:
        well_formedness_check(config_local)

    sh = sa.open(spreadsheet)
    sheets = sh.worksheets()

    if args.mode == 'generate_lex':
        repr_lemmas = create_repr_lemmas_list(config=config,
                                              config_name=config_name)
        rows = generate_lex_rows(repr_lemmas)
        repr_lemmas = pd.DataFrame(rows)
        repr_lemmas = repr_lemmas.replace(nan, '', regex=True)
        repr_lemmas = repr_lemmas[COLUMNS_OUTPUT]
        if sheet_name in [sheet.title for sheet in sheets]:
            sheet = [sheet for sheet in sheets if sheet.title == sheet_name][0]
        else:
            sheet = sh.add_worksheet(title=sheet_name, rows="100", cols="20")
        sheet.clear()
        sheet.update(
            [repr_lemmas.columns.values.tolist()] + repr_lemmas.values.tolist())
    
    elif args.mode == 'regenerate_sig':
        sheet = [sheet for sheet in sheets if sheet.title == sheet_name][0]
        regenerate_signature_lex_rows(config, config_name, sheet=sheet, sh=sh)