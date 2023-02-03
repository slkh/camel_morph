import re
import sys
import argparse
import json

import eval_utils

parser = argparse.ArgumentParser()
parser.add_argument("-config_file", default='eval_files/report_default',
                    type=str, help="Config file specifying which sheets to use.")
parser.add_argument("-msa_baseline_db", default='eval_files/calima-msa-s31_0.4.2.utf8.db',
                    type=str, help="Path of the MSA baseline DB file we will be comparing against.")
parser.add_argument("-report_dir", default='eval_files/report_default',
                    type=str, help="Paths of the directory containing partial reports generated by the full generative evaluation.")
parser.add_argument("-camel_tools", default='local', choices=['local', 'official'],
                    type=str, help="Path of the directory containing the camel_tools modules.")
args = parser.parse_args()

with open('configs/config_default.json') as f:
    config = json.load(f)

if args.camel_tools == 'local':
    camel_tools_dir = config['global']['camel_tools']
    sys.path.insert(0, camel_tools_dir)

from camel_tools.morphology.database import MorphologyDB
from camel_tools.morphology.generator import Generator

db_baseline_gen = MorphologyDB(args.msa_baseline_db, flags='g')
generator_baseline = Generator(db_baseline_gen)

db_camel_gen = MorphologyDB('databases/camel-morph-msa/XYZ_msa_all_v1.0.db', flags='g')
generator_camel = Generator(db_camel_gen)

results_debug_eval = eval_utils.get_results_debug_eval(args.report_dir)
index2lemmas_pos = eval_utils.get_index2lemmas_pos(args.report_dir)
eval_with_clitics = eval_utils.get_full_report(args.report_dir)

categorization = {}
for error_type, analyses_indexes in results_debug_eval['baseline']['not_validated'].items():
    for analysis, indexes_ in analyses_indexes.items():
        if 'neg' in analysis:
            indexes = categorization.setdefault('neg', {}).setdefault(analysis, [])
            indexes += indexes_
        elif '1+' in analysis and re.search(r'1[ps]_dobj', analysis):
            indexes = categorization.setdefault('per:1+1_dobj', {}).setdefault(analysis, [])
            indexes += indexes_
        elif re.match(r'i\+u', analysis):
            indexes = categorization.setdefault('asp:i+mod:u', {}).setdefault(analysis, [])
            indexes += indexes_
        elif 'prep' in analysis:
            indexes = categorization.setdefault('prep', {}).setdefault(analysis, [])
            indexes += indexes_
        elif re.match(r'na', analysis):
            indexes = categorization.setdefault('asp:na', {}).setdefault(analysis, [])
            indexes += indexes_
        else:
            indexes = categorization.setdefault('unk', {}).setdefault(analysis, [])
            indexes += indexes_

lemma2analysis = {}
for analysis, indexes in categorization['unk'].items():
    for index in indexes:
        lemma2analysis.setdefault(index2lemmas_pos[index], []).append(analysis)
pass