import sys
import argparse
import json
import os
import numpy as np
from tqdm import tqdm
from tabulate import tabulate
import itertools
import json

import eval_utils
from eval_utils import color, bold, underline

parser = argparse.ArgumentParser()
parser.add_argument("-config_file", default='eval_files/report_default',
                    type=str, help="Config file specifying which sheets to use.")
parser.add_argument("-pos", required=True,
                    type=str, help="Part-of-speech to perform the evaluation on.")
parser.add_argument("-db_baseline", default='eval_files/calima-msa-s31_0.4.2.utf8.db',
                    type=str, help="Path of the MSA baseline DB file we will be comparing against.")
parser.add_argument("-db_system", default='databases/camel-morph-msa/XYZ_msa_all_v1.0.db',
                    type=str, help="Path of the MSA baseline DB file we will be comparing against.")
parser.add_argument("-report_dir", default='eval_files/report_default',
                    type=str, help="Paths of the directory containing partial reports generated by the full generative evaluation.")
parser.add_argument("-baseline_name", default='Calima',
                    type=str, help="Name that will appear in the report for the baseline.")
parser.add_argument("-system_name", default='Camel',
                    type=str, help="Name that will appear in the report for the system.")
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
from camel_tools.utils.charmap import CharMapper

bw2ar = CharMapper.builtin_mapper('bw2ar')
ar2bw = CharMapper.builtin_mapper('ar2bw')

db_baseline_gen = MorphologyDB(args.db_baseline, flags='g')
generator_baseline = Generator(db_baseline_gen)

db_system_gen = MorphologyDB(args.db_system, flags='g')
generator_system = Generator(db_system_gen)

POS = eval_utils.get_pos(args.pos, db_baseline_gen, db_system_gen)
eval_utils.harmonize_defaults(generator_baseline._db, generator_system._db, POS)

try:
    results_debug_eval = eval_utils.load_results_debug_eval(args.report_dir)
except:
    pass

try:
    MATRICES = eval_utils.load_matrices(args.report_dir)

    info = MATRICES['intersection']
    diac_mat_baseline_inter = info['diac_mat_baseline']
    diac_mat_system_inter = info['diac_mat_system']
    system_only_mat_inter = info['system_only_mat']
    baseline_only_mat_inter = info['baseline_only_mat']
    no_intersect_mat_inter = info['no_intersect_mat']
    index2analysis_inter, analysis2index_inter = info['index2analysis'], info['analysis2index']
    index2lemmas_pos = {index: lemma_pos for index, lemma_pos in info['lemmas_pos']}
    failed = info['failed'] if 'failed' in info else None

    info_bo = MATRICES['baseline_only']
    diac_mat_baseline_only = info_bo['diac_mat_baseline']
    index2analysis_bo, analysis2index_bo = info_bo['index2analysis'], info_bo['analysis2index']
    index2lemmas_pos_bo = {index: lemma_pos for index, lemma_pos in info_bo['lemmas_pos']}
    failed_bo = info_bo['failed'] if 'failed' in info_bo else None

    info_so = MATRICES['system_only']
    diac_mat_system_only = info_so['diac_mat_system']
    index2analysis_so, analysis2index_so = info_so['index2analysis'], info_so['analysis2index']
    index2lemmas_pos_so = {index: lemma_pos for index, lemma_pos in info_so['lemmas_pos']}
    failed_so = info_so['failed'] if 'failed' in info_so else None
    POS2FEAT_VALUE_PAIRS = eval_utils.load_pos2feat_value_pairs(args.report_dir)
except:
    print('WARNING: Script will not work as intended and might raise errors if all three splits are not present.')

def extract_examples(match_comb_mask, index2lemmas_pos, index2analysis):
    match_comb_indexes = np.where(match_comb_mask)
    example_coord = (match_comb_indexes[0][0], match_comb_indexes[1][0])
    lemma, pos = index2lemmas_pos[example_coord[0]]
    feats = index2analysis[example_coord[1]]
    try:
        example_forms_system = generator_system.generate(
            lemma, eval_utils.construct_feats(feats, pos))
        example_forms_system = ','.join(
            set(eval_utils.preprocess_lex_features(form, True)['diac']
                for form in example_forms_system))
    except:
        example_forms_system = ''
    try:
        example_forms_baseline = generator_baseline.generate(
            lemma, eval_utils.construct_feats(feats, pos), legacy=True)
        example_forms_baseline = ','.join(
            set(eval_utils.preprocess_lex_features(form, True)['diac']
                for form in example_forms_baseline))
    except:
        example_forms_baseline = ''

    examples_str = (bold(color('lex:', 'warning')) + ar2bw(lemma) + bold(color('x', 'fail')) + '\n' +
                   bold(color('feats:', 'warning')) + '+'.join(feats) + '\n' +
                   bold(color('system:', 'warning')) + ar2bw(example_forms_system) + bold(color('x', 'fail')) + '\n' +
                   bold(color('baseline:', 'warning')) + ar2bw(example_forms_baseline)) + bold(color('x', 'fail'))
    
    return examples_str


def generate_row_for_combination(combination, match_total,
                                 diac_mat_baseline, diac_mat_system,
                                 system_only_mat, baseline_only_mat,
                                 no_intersect_mat,
                                 match_comb_mask=None):
    if len(combination) == 2:
        num_diac_baseline, num_diac_system = combination
    elif len(combination) == 3:
        num_diac_baseline, num_diac_system, _ = combination
    
    if match_comb_mask is None:
        if combination == ('≥0', '≥0', '≥1'):
            match_comb_mask = (diac_mat_baseline != 0) | (diac_mat_system != 0)
        elif combination == ('≥1', '≥1'):
            match_comb_mask = (diac_mat_baseline != 0) & (diac_mat_system != 0)
        elif combination[0] == '≥1':
            match_comb_mask = (diac_mat_baseline != 0) & (diac_mat_system == num_diac_system)
        elif combination[1] == '≥1':
            match_comb_mask = (diac_mat_baseline == num_diac_baseline) & (diac_mat_system != 0)
        else:
            match_comb_mask = (diac_mat_baseline == num_diac_baseline) & (diac_mat_system == num_diac_system)
        
    num_lemmas_match = int(np.sum(np.any(match_comb_mask, axis=1)))
    num_feats_match = int(np.sum(np.any(match_comb_mask, axis=0)))
    match_comb_sum = int(np.sum(match_comb_mask))
    if match_comb_sum == 0:
        return []

    no_intersect = int(np.sum(no_intersect_mat[match_comb_mask]))
    exact_match_indexes = ((baseline_only_mat == 0) &
                           (system_only_mat == 0) &
                           (no_intersect_mat == False) &
                           match_comb_mask)
    exact_match_indexes_sum = int(np.sum(exact_match_indexes))
    exact_match = int(np.sum(diac_mat_system[exact_match_indexes]))
    system_superset_indexes = ((system_only_mat != 0) &
                              (baseline_only_mat == 0) &
                              match_comb_mask)
    system_superset_indexes_sum = int(np.sum(system_superset_indexes))
    if all(type(c) is int for c in combination) and combination[0] >= combination[1]:
        assert system_superset_indexes_sum == 0
    system_superset_ = np.minimum(diac_mat_system[system_superset_indexes],
                                diac_mat_baseline[system_superset_indexes])
    system_superset = int(np.sum(system_superset_))
    baseline_superset_indexes = ((system_only_mat == 0) &
                                 (baseline_only_mat != 0) &
                                 match_comb_mask)
    baseline_superset_indexes_sum = int(np.sum(baseline_superset_indexes))
    if all(type(c) is int for c in combination) and combination[1] >= combination[0]:
        assert baseline_superset_indexes_sum == 0
    baseline_superset = int(np.sum(diac_mat_system[baseline_superset_indexes]))
    intersect_indexes = ((baseline_only_mat != 0) &
                         (system_only_mat != 0) &
                         match_comb_mask)
    intersect_indexes_sum = int(np.sum(intersect_indexes))
    assert np.sum(system_only_mat[intersect_indexes]) == \
           np.sum(baseline_only_mat[intersect_indexes])
    intersect = int(np.sum(system_only_mat[intersect_indexes]))
    if all(type(c) is int for c in combination):
        if combination[0] == combination[1]:
            assert exact_match == \
            np.sum(diac_mat_baseline[exact_match_indexes]) == \
            exact_match_indexes_sum * combination[0] == \
            exact_match_indexes_sum * combination[1]
            assert system_superset == baseline_superset == 0
        else:
            assert exact_match == 0
    coverage_total_x_y = int(
        no_intersect + exact_match + system_superset +
        baseline_superset + intersect)
    
    examples_str = extract_examples(match_comb_mask, index2lemmas_pos, index2analysis_inter)

    if coverage_total_x_y:
        coverage_x_y_dist = [no_intersect/coverage_total_x_y ,
                            exact_match/coverage_total_x_y,
                            baseline_superset/coverage_total_x_y,
                            system_superset/coverage_total_x_y,
                            intersect/coverage_total_x_y]
    else:
        coverage_x_y_dist = [no_intersect, exact_match, baseline_superset,
                             system_superset, intersect]
    slot_total_x_y = (no_intersect + exact_match_indexes_sum +
                      baseline_superset_indexes_sum +
                      system_superset_indexes_sum +
                      intersect_indexes_sum)
    assert slot_total_x_y == match_comb_sum
    slot_x_y_dist = [no_intersect/slot_total_x_y,
                     exact_match_indexes_sum/slot_total_x_y,
                     baseline_superset_indexes_sum/slot_total_x_y,
                     system_superset_indexes_sum/slot_total_x_y,
                     intersect_indexes_sum/slot_total_x_y]
    coverage_highest_index = np.array(coverage_x_y_dist).argmax()
    slot_highest_index = np.array(slot_x_y_dist).argmax()
    coverage_x_y_dist_str = [
        (f'{x:.1%}' if i != coverage_highest_index else bold(color(f'{x:.1%}', 'green'))) +
        ((f'\n{y:.1%}' if i != slot_highest_index else '\n' + bold(color(f'{y:.1%}', 'cyan'))) if x != y else '')
        for i, (x, y) in enumerate(zip(coverage_x_y_dist, slot_x_y_dist))]

    total_diac_baseline = int(np.sum(diac_mat_baseline[match_comb_mask]))
    total_diac_system = int(np.sum(diac_mat_system[match_comb_mask]))
    if all(type(c) is int for c in combination):
        assert slot_total_x_y * combination[0] == total_diac_baseline
    if total_diac_baseline != 0 and total_diac_system != 0:
        recall_diac = (coverage_total_x_y - no_intersect) / total_diac_baseline
        recall_slot = (slot_total_x_y - no_intersect) / match_comb_sum
        recall_diac_str, recall_slot_str = f'{recall_diac:.1%}', f'{recall_slot:.1%}'
    else:
        recall_diac, recall_slot = 'N/A', 'N/A'
        recall_diac_str, recall_slot_str = recall_diac, recall_slot

    return [combination[0], combination[1],
            f'{match_comb_sum:,}' + '\n' + f'({match_comb_sum/match_total:.1%})',
            f'{num_lemmas_match:,}' + '\n' + f'({num_lemmas_match/num_valid_lemmas:.1%})',
            f'{num_feats_match:,}' + '\n' + f'({num_feats_match/num_valid_feats:.1%})',
            examples_str,
            *coverage_x_y_dist_str,
            bold(color(recall_diac_str, 'blue')) +
            (('\n' + bold(color(recall_slot_str, 'blue')) if recall_diac != recall_slot else ''))]


db_baseline = MorphologyDB(args.db_baseline)
db_system = MorphologyDB(args.db_system)
POS = eval_utils.get_pos(args.pos, db_baseline, db_system)
del db_system

report_title = f"Evaluation Report - {' '.join(pos.upper() for pos in POS)}"
try:
    terminal_size_col = os.get_terminal_size().columns
except:
    terminal_size_col = len(report_title)
print()
print('=' * terminal_size_col)
print(report_title)
print('=' * terminal_size_col)
print()
baseline_path = color(bold(args.db_baseline), 'cyan')
system_path = color(bold(args.db_system), 'cyan')
print(bold(underline('DBs used for analysis')))
print(f'{args.baseline_name}: ' + color(bold(args.db_baseline), 'cyan'))
print(f'{args.system_name}: ' + color(bold(args.db_system), 'cyan'))
print()
print(bold(underline(f'Verb Lemmas overlap between {args.baseline_name} and {args.system_name}')))
print()
lemmas_pos_baseline = eval_utils.get_all_lemmas_from_db(db_baseline)
del db_baseline
lemmas_baseline = set([lemma_pos[0] for lemma_pos in lemmas_pos_baseline if lemma_pos[1] in POS])
lemmas_pos_system = eval_utils.get_all_lemmas_from_db(MorphologyDB(args.db_system))
lemmas_system = set([lemma_pos[0] for lemma_pos in lemmas_pos_system if lemma_pos[1] in POS])
rows = []
header = ['A . B', 'Result', '# lemmas', '(%)', 'Lemmas']
lemmas_baseline_only = lemmas_baseline - lemmas_system
lemmas_system_only = lemmas_system - lemmas_baseline
lemmas_intersect = lemmas_system & lemmas_baseline
lemmas_union = lemmas_system | lemmas_baseline
rows.append([f'{args.baseline_name} - {args.system_name}',
             f'{len(lemmas_baseline_only):,}',
             f'{len(lemmas_baseline):,} in A',
             f'{len(lemmas_baseline_only) / len(lemmas_baseline):.2%}',
             ' '.join(sorted(map(ar2bw, lemmas_baseline_only)))])
rows.append([f'{args.system_name} - {args.baseline_name}',
             f'{len(lemmas_system_only):,}',
             f'{len(lemmas_system):,} in A',
             f'{len(lemmas_system_only) / len(lemmas_system):.2%}',
             ' '.join(sorted(map(ar2bw, lemmas_system_only)))])
rows.append([f'{args.system_name} ∩ {args.baseline_name}',
             bold(color(f'{len(lemmas_intersect):,}', 'green')),
             f'{len(lemmas_union):,} in A ∪ B',
             f'{len(lemmas_intersect) / len(lemmas_union):.2%}',
             '-'])
print(tabulate(rows, tablefmt='fancy_grid', headers=header, maxcolwidths=[None, None, None, None, 100]))
print()
print(bold(underline(f'Overlap statistics of generated diacs between {args.baseline_name} and {args.system_name}')))
print()

mask_not_equal_0_baseline = diac_mat_baseline_inter != 0
mask_not_equal_0_system = diac_mat_system_inter != 0

rows = []
num_valid_feats = int(np.sum(np.any(diac_mat_system_inter|diac_mat_baseline_inter, axis=0)))
num_valid_lemmas = int(np.sum(np.any(diac_mat_system_inter|diac_mat_baseline_inter, axis=1)))
slots_total = num_valid_feats * num_valid_lemmas
slots_filled_mask = mask_not_equal_0_system | mask_not_equal_0_baseline
slots_filled_total = int(np.sum(slots_filled_mask))

examples_str = extract_examples(slots_filled_mask, index2lemmas_pos, index2analysis_inter)
rows.append(['Number of slots filled by at least one of the systems (0-x, x-0, x-y)',
             bold(color(f'{slots_filled_total:,}', 'warning')),
             f'{slots_filled_total/slots_total:.0%}',
             examples_str])
examples_str = extract_examples(~slots_filled_mask, index2lemmas_pos, index2analysis_inter)
rows.append(['Number of slots filled by none of the systems (0-0)',
             f'{slots_total - slots_filled_total:,}',
             f'{(slots_total - slots_filled_total)/slots_total:.0%}',
             examples_str])
rows.append(['Total number of slots per system',
             f'{slots_total:,}' + '\n(' + bold(color(f'{num_valid_lemmas:,} ', 'green')) + '× ' +
             bold(color(f'{num_valid_feats:,}', 'green')) + ')',
             f'{1:.0%}', '-'])
assert len(diac_mat_baseline_inter) == len(diac_mat_system_inter)
print('Number of lemmas evaluated on: ' + bold(color(f'{len(diac_mat_baseline_inter):,}', 'green')) +
      f' ({args.system_name} ∩ {args.baseline_name})')
print('Total number of feature combinations across both systems: ' + bold(color(f'{num_valid_feats:,}', 'green')))
print(tabulate(rows, tablefmt='fancy_grid', maxcolwidths=[40, None, None, 40]))
print()
print(bold(underline(f'Distribution of feature combination availability across systems for ')) +
      bold(underline(color('SHARED', 'orange'))) + bold(underline(f' feature combination pairs (0-x, x-0, x-y)')))

notes = color(f"""
Notes:
    - # diac here is the number of unique diacs generated, and not the number of analyses generated which could generally be more.
    - The meaning of the dash ("-") is anything but zero.
    - A "slot" is a matrix cell representing a lemma and a feature combinatinon from which one a more diacs were generated.
    - "Slot space" means we are counting number of slots while in diac space were are counting number of diacs. This effectively means that
    the # diac is taken as 1 for the purpose of recall analysis.
    - Slots column is the number of feature combinations that both systems were able to generate for listed lemmas with the specified number of diacs.
    - Lemmas column is the number of lemmas with which at least one feature combination generates with the specified number of diacs.
    - Top number in recall distribution (last columns) indicates recall (diac space) by {args.system_name} of {args.baseline_name} and bottom is in slot space
      (displayed only if different). Total recall in slot space basically represents the sum of all categories (in slot space) minus no_intersect.
    - All total recall values are micro-averaged.
""", 'warning')
print(notes)
print()

rows = []
header = [f'# diac ({args.baseline_name})', f'# diac ({args.system_name})',
          'Slots', 'Lemmas', 'Feat combs', 'Example', 'Recall baseline (micro)',
          'Recall system (micro)']

match_total = int(np.sum(mask_not_equal_0_baseline | mask_not_equal_0_system))
combinations = [(0, '≥1'), ('≥1', 0), ('≥1', '≥1'), ('≥0', '≥0', '≥1')]
for combination in tqdm(combinations, ncols=100):
    row = generate_row_for_combination(combination, match_total,
                                       diac_mat_baseline=diac_mat_baseline_inter,
                                       diac_mat_system=diac_mat_system_inter,
                                       system_only_mat=system_only_mat_inter,
                                       baseline_only_mat=baseline_only_mat_inter,
                                       no_intersect_mat=no_intersect_mat_inter)
    if row:
        rows.append(row)

rows = sorted(rows, key=lambda row: int(row[2].split('\n')[0].replace(',', ''))
              if row[0] != '≥0' else -1,
              reverse=True)
rows = [row[:6] + row[11:] for row in rows]
match_x_y_index = [i for i, row in enumerate(rows) if row[0] == row[1] == '≥1'][0]
match_all_index = [i for i, row in enumerate(rows) if row[0] == row[1] == '≥0'][0]
rows[match_x_y_index][2] = (bold(color(rows[match_x_y_index][2].split('\n')[0], 'cyan')) + '\n' +
                            bold(rows[match_x_y_index][2].split('\n')[1]))
rows[match_x_y_index][3] = (bold(color(rows[match_x_y_index][3].split('\n')[0], 'orange')) + '\n' +
                            bold(rows[match_x_y_index][3].split('\n')[1]))
rows[match_x_y_index][4] = (bold(color(rows[match_x_y_index][4].split('\n')[0], 'orange')) + '\n' +
                            bold(rows[match_x_y_index][4].split('\n')[1]))
rows[match_all_index][2] = (bold(color(rows[match_all_index][2].split('\n')[0], 'warning')) + '\n' +
                            bold(rows[match_all_index][2].split('\n')[1]))
rows[match_all_index][3] = (color(rows[match_all_index][3].split('\n')[0], 'green') + '\n' +
                            bold(rows[match_all_index][3].split('\n')[1]))
rows[match_all_index][4] = (color(rows[match_all_index][4].split('\n')[0], 'green') + '\n' +
                            bold(rows[match_all_index][4].split('\n')[1]))
rows[match_all_index][-1] = bold(color('N/A', 'blue'))
rows[-1] = [bold(v) for v in rows[-1]]

print(tabulate(rows, tablefmt='fancy_grid', headers=header,
               maxheadercolwidths=[8, 7, None, None, 7, 40, 12, 12]))

print()
print(bold(underline(f'Distribution of feature combination availability across systems for ')) +
      bold(underline(color('UNSHARED', 'orange'))) + bold(underline(f' feature combination pairs (0-x, x-0)')))
notes = color(f"""
Notes:
- The unshared feature combination pairs can be divided into two groups:
    1. The ones which contain individual feat:value pairs that are never seen in the opposite systems.
    2. The ones which contain sub-combinations of feat:value pairs that are never seen in the opposite system
- The last column of the below table lists the ones of the first group. Second group is dealt with in the next section.
""", 'warning')
print(notes)
rows = []
header = [f'# diac ({args.baseline_name})', f'# diac ({args.system_name})',
          'Slots', 'Lemmas', 'Feats', 'Example', 'Unshared feats']

def get_clitic_feats_str(clitic_feats):
    pos2clitic_feats = {}
    for feat, value, pos in clitic_feats:
        pos2clitic_feats.setdefault(pos, set()).add(f'{feat}:{value}')
    
    clitic_feats_str = '; '.join(pos.upper() + '(' + ' '.join(sorted(clitic_feats)) + ')'
                                for pos, clitic_feats in pos2clitic_feats.items())
    return clitic_feats_str

# for system_, pos2feat_value_pairs in POS2FEAT_VALUE_PAIRS:
pos2feat_value_pairs_baseline = POS2FEAT_VALUE_PAIRS['baseline']
feat_value_pairs_baseline = set([tuple(feat_value_pair.split(':')) + (pos,)
                                 for pos, feat_value_pairs in pos2feat_value_pairs_baseline.items()
                                 for feat_value_pair in feat_value_pairs])
pos2feat_value_pairs_system = POS2FEAT_VALUE_PAIRS['system']
feat_value_pairs_system = set([tuple(feat_value_pair.split(':')) + (pos,)
                               for pos, feat_value_pairs in pos2feat_value_pairs_system.items()
                               for feat_value_pair in feat_value_pairs])
# This is not intersection of the feat:value pairs of the intersction matrix feat_combs
# but is the intersection of common feat:value pairs in both systems (whether they occur
# in the above or not e.g., >a_ques does not occur in the 3828 combs intersection for verbs
# but occurs in both systems individually, hence it will occur in the below variable).
# Might need to change this if we want to enable an automatic discovery of mismatching feat:value
# pairs.
feat_value_pairs_intersect = feat_value_pairs_baseline & feat_value_pairs_system

feat_value_pairs_baseline_only = feat_value_pairs_baseline - feat_value_pairs_intersect
feat_value_pairs_system_only = feat_value_pairs_system - feat_value_pairs_intersect

feat2index = {feat: i for i, feat in enumerate(eval_utils.essential_keys_no_lex_pos)}

def get_dist_over_feats(feat_value_pairs, diac_mat, index2analysis, specific_feat_combs):
    # Contains for each feat:value the analyses (from possible combinations) that contain it
    feat_value2queries = {}
    for feat, value, pos in feat_value_pairs:
        #NOTE: not using POS, might be problematic for OTHER
        for i, feats in enumerate(index2analysis):
            if feats[feat2index[feat]] == value:
                feat_value2queries.setdefault((feat, value), []).append(i)
    # Contains for each feat:value the number of slots it occupies
    feat_value2slots = {}
    for (feat, value), queries in feat_value2queries.items():
        queries = np.array(queries)
        queries_valie_slots = diac_mat[:, queries]
        feat_value2slots[(feat, value)] = np.sum(queries_valie_slots)
    # Contains all the feat_combs in which the feat:value pairs participate
    feat_combs_group_1_indexes = set.union(*map(set, feat_value2queries.values()))
    # Contains all the feat_combs which do not have any of these feat:value pairs
    # but which are still unique to that system. These might either be invalid OR
    # mappable to one(s) in that of another system.
    feat_combs_group_2_indexes = [i for i in range(len(index2analysis))
                                      if i not in feat_combs_group_1_indexes]
    feat_combs_group_2 = [feats for i, feats in enumerate(index2analysis)
                                      if i in feat_combs_group_2_indexes]
    group_2_categorization = {}
    for feat_comb in feat_combs_group_2:
        for info in specific_feat_combs:
            feats_dict = info['feats_dict']
            invalid = True
            for f, v_rule in feats_dict.items():
                v = feat_comb[feat2index[f]]
                match = False
                for v_rule_ in v_rule.split('+'):
                    match = match or (v_rule_[0] == '!' and v != v_rule_[1:] or
                                      v_rule_[0] != '!' and v == v_rule_)
                invalid = invalid and match
            if invalid:
                break
        if invalid:
            group_2_categorization.setdefault(
                ' '.join(sorted(f'{f}:{v}' for f, v in info['feats_dict'].items())), []).append(feat_comb)
    assert sum(len(feats) for feats in group_2_categorization.values()) == len(feat_combs_group_2)
    assert len(specific_feat_combs) == len(group_2_categorization)
    
    return group_2_categorization


with open(os.path.join(args.report_dir, 'calima_specific_feat_combs.json')) as f:
    specific_feat_combs_baseline = json.load(f)
with open(os.path.join(args.report_dir, 'camel_specific_feat_combs.json')) as f:
    specific_feat_combs_system = json.load(f)

group_2_categorization_bo = get_dist_over_feats(
    feat_value_pairs_baseline_only, diac_mat_baseline_only, index2analysis_bo, specific_feat_combs_baseline)
group_2_categorization_so = get_dist_over_feats(
    feat_value_pairs_system_only, diac_mat_system_only, index2analysis_so, specific_feat_combs_system)

feat_value_pairs_baseline_only_str = get_clitic_feats_str(feat_value_pairs_baseline_only)
feat_value_pairs_system_only_str = get_clitic_feats_str(feat_value_pairs_system_only)

unshared_so_mask, unshared_bo_mask  = diac_mat_system_only != 0, diac_mat_baseline_only != 0
unshared_so_mask_zero, unshared_bo_mask_zero  = diac_mat_system_only == 0, diac_mat_baseline_only == 0
unshared_so_sum, unshared_bo_sum = np.sum(unshared_so_mask), np.sum(unshared_bo_mask)
num_lemmas_valid_so = np.sum(np.any(unshared_so_mask, axis=1))
num_lemmas_valid_bo = np.sum(np.any(unshared_bo_mask, axis=1))
num_feats_valid_so = np.sum(np.any(unshared_so_mask, axis=0))
num_feats_valid_bo = np.sum(np.any(unshared_bo_mask, axis=0))
examples_str_so = extract_examples(unshared_so_mask, index2lemmas_pos_so, index2analysis_so)
examples_str_bo = extract_examples(unshared_bo_mask, index2lemmas_pos_bo, index2analysis_bo)
examples_str_so_zero = extract_examples(unshared_so_mask_zero, index2lemmas_pos_so, index2analysis_so)
examples_str_bo_zero = extract_examples(unshared_bo_mask_zero, index2lemmas_pos_bo, index2analysis_bo)
unshared_so_total = diac_mat_system_only.shape[0] * diac_mat_system_only.shape[1]
unshared_bo_total = diac_mat_baseline_only.shape[0] * diac_mat_baseline_only.shape[1]

feat_combs_indexes_so = np.array([analysis2index_so[feat_comb]
                                 for feat_combs in group_2_categorization_so.values()
                                 for feat_comb in feat_combs])
feat_combs_indexes_bo = np.array([analysis2index_bo[feat_comb]
                                 for feat_combs in group_2_categorization_bo.values()
                                 for feat_comb in feat_combs])
group_2_mask_so = diac_mat_system_only[:, feat_combs_indexes_so] != 0
group_2_mask_bo = diac_mat_baseline_only[:, feat_combs_indexes_bo] != 0
group_2_sum_so = int(np.sum(group_2_mask_so))
group_2_sum_bo = int(np.sum(group_2_mask_bo))


rows.append([0, '≥1\n(group 1)',
          f'{unshared_so_sum - group_2_sum_so:,}' + '\n' + f'({(unshared_so_sum - group_2_sum_so)/unshared_so_sum:.1%})',
          '-', '-', '-', '-'])
rows.append([0, '≥1\n(group 2)',
          bold(color(f'{group_2_sum_so:,}', 'orange')) + '\n' + bold(f'({group_2_sum_so/unshared_so_sum:.1%})'),
          '-', '-', '-', feat_value_pairs_system_only_str])
rows.append([0, '≥1\n(all)',
          f'{unshared_so_sum:,}' + '\n' + f'({unshared_so_sum/unshared_so_total:.1%})',
          f'{num_lemmas_valid_so:,}' + '\n' + f'({num_lemmas_valid_so/diac_mat_system_only.shape[0]:.1%})',
          f'{num_feats_valid_so:,}' + '\n' + f'({num_feats_valid_so/diac_mat_system_only.shape[1]:.1%})',
          examples_str_so, '-'])
rows.append(['0\n(system)', '0\n(system)',
          f'{unshared_so_total - unshared_so_sum:,}' + '\n' + f'({(unshared_so_total - unshared_so_sum)/unshared_so_total:.1%})',
          '-', '-', examples_str_so_zero, '', ''])
rows.append(['≥1\n(group 1)', 0,
          f'{unshared_bo_sum - group_2_sum_bo:,}' + '\n' + f'({(unshared_bo_sum - group_2_sum_bo)/unshared_bo_sum:.1%})',
          '-', '-', '-', '-'])
rows.append(['≥1\n(group 2)', 0,
          bold(color(f'{group_2_sum_bo:,}', 'orange')) + '\n' + bold(f'({group_2_sum_bo/unshared_bo_sum:.1%})'),
          '-', '-', '-', '-'])
rows.append(['≥1\n(all)', 0,
          f'{unshared_bo_sum:,}' + '\n' + f'({unshared_bo_sum/unshared_bo_total:.1%})',
          f'{num_lemmas_valid_bo:,}' + '\n' + f'({num_lemmas_valid_bo/diac_mat_baseline_only.shape[0]:.1%})',
          f'{num_feats_valid_bo:,}' + '\n' + f'({num_feats_valid_bo/diac_mat_baseline_only.shape[1]:.1%})',
          examples_str_bo, feat_value_pairs_baseline_only_str])
rows.append(['0\n(baseline)', '0\n(baseline)',
          f'{unshared_bo_total - unshared_bo_sum:,}' + '\n' + f'({(unshared_bo_total - unshared_bo_sum)/unshared_bo_total:.1%})',
          '-', '-', examples_str_bo_zero, '', ''])

print(tabulate(rows, tablefmt='fancy_grid', headers=header,
               maxheadercolwidths=[13, 13, None, None, None, None, 50],
               maxcolwidths=[None, None, None, None, None, None, 50]))

print()
print(bold(underline(f'Breakdown of the (mappable, invalid, or missing) x-0 and 0-x cases')))
notes = color(f"""
Notes:
- The below table breaks down the second group of unshared features (described above).
- When all feature combinations that contain one of the unshared feat:value pairs are eliminated, we are left with three groups of feature sub-combinations:
    1. ones which can be mappable to feature combinations in the opposite system
    2. ones which should just not exist
    3. ones which are missing in the opposite system
- Every single one of these feature combinations is accounted for automatically by elimination via human identification of the culprit feat:value
pair(s) which make that feature combination not appear in the opposite system.
- Feats column below is used differently than previous Feats columns and is used to specify the number of feature combinations in which
the respective sub-combination happens.
""", 'warning')
print(notes)
rows = []
header = [f'# diac ({args.baseline_name})', f'# diac ({args.system_name})',
          'Features', 'Slots', 'Lemmas', 'Feats', 'Explanation']
for i, specific_feat_combs in enumerate([specific_feat_combs_baseline, specific_feat_combs_system]):
    rows_ = []
    total_sum = 0
    analysis2index = analysis2index_so if i else analysis2index_bo
    group_2_categorization = group_2_categorization_so if i else group_2_categorization_bo
    diac_mat_ = diac_mat_system_only if i else diac_mat_baseline_only
    num_lemmas = diac_mat_system_only.shape[0] if i else diac_mat_baseline_only.shape[0]
    num_feats = diac_mat_system_only.shape[1] if i else diac_mat_baseline_only.shape[1]
    total_feat_combs = sum(len(feats) for feats in group_2_categorization.values())
    feat_combs_indexes = feat_combs_indexes_so if i else feat_combs_indexes_bo
    total = int(np.sum(diac_mat_[:, feat_combs_indexes] != 0))
    for info in specific_feat_combs:
        unshared_feat_subcombs = ' '.join(sorted(f'{f}:{v}' for f, v in info['feats_dict'].items()))
        feat_combs_indexes_ = np.array([analysis2index[feats]
                                      for feats in group_2_categorization[unshared_feat_subcombs]])
        group_2_mask = diac_mat_[:, feat_combs_indexes_] != 0
        
        num_slots = int(np.sum(group_2_mask))
        total_sum += num_slots
        num_lemmas_valid = int(np.sum(np.any(group_2_mask, axis=1)))
        num_feats_valid = len(group_2_categorization[unshared_feat_subcombs])
        
        row = [('0' if i else '≥1'), ('≥1' if i else '0'),
               unshared_feat_subcombs,
               f'{num_slots:,}' + '\n' + f'({num_slots/total:.1%})',
               f'{num_lemmas_valid:,}' + '\n' + f'({num_lemmas_valid/num_lemmas:.1%})',
               f'{num_feats_valid:,}' + '\n' + f'({num_feats_valid/total_feat_combs:.1%})',
               info['explanation']]
        rows_.append(row)
    
    rows += sorted(rows_, key=lambda row: int(row[3].split('\n')[0].replace(',', '')),
                   reverse=True)
    assert total == total_sum
    rows.append([('0' if i else '≥1'), ('≥1' if i else '0'),
                bold(color('Total', 'orange')),
                bold(color(f'{total_sum:,}', 'orange')) + '\n' + bold(f'({total_sum/total:.1%})'),
                '-', '-', '-'])

print(tabulate(rows, tablefmt='fancy_grid', headers=header,
               maxheadercolwidths=[8, 7, None, None, None, 50, 50],
               maxcolwidths=[8, 7, None, None, None, 50, 50]))

print()
print(bold(underline(f'Summary breakdown of the x-y set (coverage of {args.baseline_name} by {args.system_name})')))
print()
combinations = [
    ((1, '>1'), (diac_mat_baseline_inter == 1) & (diac_mat_system_inter > 1)),
    (('>1', 1), (diac_mat_baseline_inter > 1) & (diac_mat_system_inter == 1)),
    ((1, 1), (diac_mat_baseline_inter == 1) & (diac_mat_system_inter == 1)),
    (('x>1', 'y>1'), (diac_mat_baseline_inter > 1) & (diac_mat_system_inter > 1) & (diac_mat_system_inter != diac_mat_baseline_inter)),
    (('x>1', 'x>1'), (diac_mat_baseline_inter > 1) & (diac_mat_system_inter > 1) & (diac_mat_system_inter == diac_mat_baseline_inter)),
    (('≥1', '≥1'), (diac_mat_baseline_inter != 0) & (diac_mat_system_inter != 0)),
]

rows = []
header = [f'# diac ({args.baseline_name})', f'# diac ({args.system_name})',
          'Slots', 'Lemmas', 'Feat combs', 'Example', 'No intersec', 'Exact match',
          f'{args.baseline_name} super', f'{args.system_name} super', 'Intersec',
          'Recall baseline (micro)', 'Recall system (micro)']

match_x_y_total = int(np.sum(mask_not_equal_0_baseline & mask_not_equal_0_system))
for combination, match_comb_mask in tqdm(combinations, ncols=100):
    row = generate_row_for_combination(combination, match_x_y_total,
                                       diac_mat_baseline=diac_mat_baseline_inter,
                                       diac_mat_system=diac_mat_system_inter,
                                       system_only_mat=system_only_mat_inter,
                                       baseline_only_mat=baseline_only_mat_inter,
                                       no_intersect_mat=no_intersect_mat_inter,
                                       match_comb_mask=match_comb_mask)
    if row:
        rows.append(row)

rows = sorted(rows, key=lambda row: int(row[2].split('\n')[0].replace(',', ''))
              if row[0] != '≥1' else -1,
              reverse=True)
rows[-1][2] = bold(color(rows[-1][2].split('\n')[0], 'cyan')) + '\n' + \
              bold(rows[-1][2].split('\n')[1])
rows[-1][3] = bold(color(rows[-1][3].split('\n')[0], 'orange')) + '\n' + \
              bold(rows[-1][3].split('\n')[1])
rows[-1][4] = bold(color(rows[-1][4].split('\n')[0], 'orange')) + '\n' + \
              bold(rows[-1][4].split('\n')[1])
rows[-1] = [bold(v) for v in rows[-1]]

print(tabulate(rows, tablefmt='fancy_grid', headers=header,
               maxheadercolwidths=[8, 7, None, None, 9, 40, 8, 7, 8, 7, 8, 12, 12],
               maxcolwidths=[8, 7, None, None, 9, 40, 8, 7, 8, 7, 8, None, None]))
print()