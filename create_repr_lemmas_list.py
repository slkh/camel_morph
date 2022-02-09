import argparse
import json
import os
import pickle
import numpy as np

from camel_tools.utils.charmap import CharMapper
from camel_tools.morphology.utils import strip_lex
from camel_tools.morphology.database import MorphologyDB
from camel_tools.morphology.analyzer import Analyzer

import db_maker

nominals = ["ABBREV", "ADJ", "ADJ_COMP", "ADJ_NUM", "ADV",
            "ADV_INTERROG", "ADV_REL",
            "FORIEGN", "INTERJ", "NOUN", "NOUN_NUM",
            "NOUN_PROP", "NOUN_QUANT",
            "PRON", "PRON_DEM", "PRON_EXCLAM", "PRON_INTERROG",
            "PRON_REL", "VERB_NOM", "VERB_PSEUDO"]
nominals = [n.lower() for n in nominals]

ar2bw = CharMapper.builtin_mapper('ar2bw')
bw2ar = CharMapper.builtin_mapper('bw2ar')
db = MorphologyDB.builtin_db()
analyzer = Analyzer(db)

def create_repr_lemmas_list(config_file,
                            config_name,
                            pos_type):
    with open(config_file) as f:
        config = json.load(f)
    SHEETS, _ = db_maker.read_morph_specs(config, config_name)

    lemmas_uniq = {}
    for _, row in SHEETS['lexicon'].iterrows():
        feats = tuple(row['FEAT'].split())
        if 'vox:p' in feats:
            continue
        lemmas_uniq.setdefault(row['LEMMA'], []).append(
            (row['COND-T'], row['COND-S'], feats, row['FORM'], row['GLOSS']))
    uniq_lemma_classes = {}
    for lemma, stems in lemmas_uniq.items():
        lemmas_cond_sig = tuple([stem[:3] for stem in stems])
        feats = {}
        for stem in stems:
            stem_feats = {
                feat.split(':')[0]: feat.split(':')[1] for feat in stem[2]}
            for feat, value in stem_feats.items():
                if feats.get(feat) != None and value != feats[feat]:
                    feats[feat] += f'+{value}'
                else:
                    feats[feat] = value
        form = ''.join(
            set([(f"[{stem[3]}]"
                  f"({sum(1 for stem_ in stems if stem_[3] == stem[3])})") for stem in stems]))
        cond_t = ''.join(
            set([(f"[{stem[0] if stem[0] else '—'}]"
                  f"({sum(1 for stem_ in stems if stem_[0] == stem[0])})") for stem in stems]))
        cond_s = ''.join(
            set([(f"[{stem[1] if stem[1] else '—'}]"
                  f"({sum(1 for stem_ in stems if stem_[1] == stem[1])})") for stem in stems]))
        info = dict(form=form,
                    lemma=lemma.split(':')[1],
                    cond_t=cond_t,
                    cond_s=cond_s,
                    pos=feats['pos'],
                    gen=feats['gen'],
                    num=feats['num'],
                    gloss=stem[4])
        uniq_lemma_classes.setdefault(lemmas_cond_sig, {'freq': 0, 'lemmas': []})
        uniq_lemma_classes[lemmas_cond_sig]['freq'] += 1
        uniq_lemma_classes[lemmas_cond_sig]['lemmas'].append(info)
    
    lemma2prob = {}
    for lemmas_cond_sig, lemmas_info in uniq_lemma_classes.items():
        for info in lemmas_info['lemmas']:
            lemma_ar = bw2ar(strip_lex(info['lemma']))
            analyses = analyzer.analyze(lemma_ar)
            if pos_type == 'verbal':
                analyses_filtered = [a  for a in analyses
                    if a['lex'] == lemma_ar and a['pos'] == 'verb' and
                    a['per'] == '3' and a['num'] == 's' and a['gen'] == 'm' and
                    a['stemgloss'] == info['gloss']]
            #TODO: update this before generating for nouns
            elif pos_type == 'nominal':
                analyses_filtered = [a  for a in analyses
                    if a['pos'] in nominals and
                    a['stemgloss'] == info['gloss']]
            lemma2prob[info['lemma']] = analyses_filtered

    for lemma, analyses in lemma2prob.items():
        if len(analyses) > 1:
            assert len(set([a['lex'] for a in analyses])) == 1, 'Cannot discard analysis'
            lemma2prob[lemma] = [analyses[0]]
    for lemma, analyses in lemma2prob.items():
        if len(analyses) <= 1:
            if len(analyses) == 1:
                lemma2prob[lemma] = analyses[0]['pos_lex_logprob']
            else:
                lemma2prob[lemma] = -99.0
        else:
            raise 'Still more than one analysis after filtering and discarding'
    
    assert all([any([True if info['lemma'] in lemma2prob else False for info in lemmas_info['lemmas']])
        for lemmas_info in uniq_lemma_classes.values()]), \
            'Some classes do not contain any representative after filtering'
    
    for lemmas_cond_sig, lemmas_info in uniq_lemma_classes.items():
        lemmas = [info['lemma'] for info in lemmas_info['lemmas']]
        best_index = int(np.array([lemma2prob[lemma] for lemma in lemmas]).argmax())
        best_lemma_info = lemmas_info['lemmas'][best_index]
        best_lemma_info['freq'] = lemmas_info['freq']
        uniq_lemma_classes[lemmas_cond_sig] = best_lemma_info
        
    return uniq_lemma_classes


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-config_file", required=True,
                        type=str, help="Config file specifying which sheets to use from `specs_sheets`.")
    parser.add_argument("-config_name", required=True,
                        type=str, help="Name of the configuration to load from the config file.")
    parser.add_argument("-output_dir", default='conjugation/repr_lemmas',
                        type=str, help="Path of the directory to output the lemmas to.")
    parser.add_argument("-output_name", required=True,
                        type=str, help="Name of the file to output the representative lemmas to. File will be placed in a directory called conjugation/repr_lemmas/")
    parser.add_argument("-pos_type", required=True, choices=['verbal', 'nominal'],
                        type=str, help="POS type of the lemmas.")
    args = parser.parse_args([] if "__file__" not in globals() else None)

    conj_dir = args.output_dir.split('/')[0]
    if not os.path.exists(conj_dir):
        os.mkdir(conj_dir)
        os.mkdir(args.output_dir)
    elif not os.path.exists(args.output_dir):
        os.mkdir(args.output_dir)

    uniq_lemma_classes = create_repr_lemmas_list(config_file=args.config_file,
                                                 config_name=args.config_name,
                                                 pos_type=args.pos_type)

    output_path = os.path.join(args.output_dir, args.output_name)
    with open(output_path, 'wb') as f:
        pickle.dump(uniq_lemma_classes, f)
        
