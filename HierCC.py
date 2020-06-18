#!/usr/bin/env python

# HierCC.py
# Hierarchical Clustering Complex of MLST allelic profiles
#
# Author: Zhemin Zhou
# Lisence: GPLv3
#
# New assignment: hierCC.py -p <allelic_profile> -o <output_prefix>
# Incremental assignment: hierCC.py -p <allelic_profile> -o <output_prefix> -i <old_cluster_npy>
# Input format:
# ST_id gene1 gene2
# 1 1 1
# 2 1 2
# ...

import sys, gzip, argparse, logging
import pandas as pd, numpy as np
from multiprocessing import Pool
from scipy.spatial import distance as ssd
from scipy.cluster.hierarchy import linkage
try :
    from getDistance import getDistance
except :
    from .getDistance import getDistance

logging.basicConfig(format='%(asctime)s | %(message)s',stream=sys.stdout, level=logging.INFO)


def get_args(args):
    parser = argparse.ArgumentParser(description='''HierCC takes allelic profile (as in https://pubmlst.org/data/) and
work out hierarchical clusters of all the profiles based on a minimum-spanning tree.''',
                                     formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('-p', '--profile', help='[INPUT; REQUIRED] name of the profile file. Can be GZIPed.',
                        required=True)
    parser.add_argument('-o', '--output',
                        help='[OUTPUT; REQUIRED] Prefix for the output files. These include a NUMPY and TEXT verions of the same clustering result',
                        required=True)
    parser.add_argument('-a', '--append', help='[INPUT; optional] The NUMPY version of an existing HierCC result',
                        default='')
    return parser.parse_args(args)


def prepare_mat(profile_file) :
    mat = pd.read_csv(profile_file, sep='\t', header=None, dtype=str).values
    allele_columns = np.array([i == 0 or (not h.startswith('#')) for i, h in enumerate(mat[0])])
    mat = mat[1:, allele_columns].astype(int)
    mat = mat[mat.T[0]>0]
    return mat


def hierCC(args):
    params = get_args(args)
    pool = Pool(10)

    profile_file, cluster_file, old_cluster = params.profile, params.output + '.npz', params.append

    mat = prepare_mat(profile_file)
    n_loci = mat.shape[1] - 1

    logging.info(
        'Loaded in allelic profiles with dimension: {0} and {1}. The first column is assumed to be type id.'.format(
            *mat.shape))
    logging.info('Start hierCC assignments')

    # prepare existing clusters
    if not params.append:
        absence = np.sum(mat <= 0, 1)
        mat[:] = mat[np.argsort(absence, kind='mergesort')]
        typed = {}
    else :
        od = np.load(old_cluster, allow_pickle=True)
        cls = od['hierCC']
        typed = {c: id for id, c in enumerate(cls.T[0]) if c > 0}
    if len(typed) > 0:
        logging.info('Loaded in {0} old hierCC assignments.'.format(len(typed)))
        mat_idx = np.array([t in typed for t in mat.T[0]])
        mat[:] = np.vstack([mat[mat_idx], mat[(mat_idx) == False]])
        start = np.sum(mat_idx)
    else :
        start = 0

    res = np.repeat(mat.T[0], int(mat.shape[1]) + 1).reshape(mat.shape[0], -1)
    res[res < 0] = np.max(mat.T[0]) + 100
    res.T[0] = mat.T[0]
    logging.info('Calculate distance matrix')
    # prepare existing tree
    if params.append :
        for r in res :
            if r[0] in typed :
                r[:] = cls[typed[r[0]]]
    else :
        with getDistance(mat, 'syn_dist', pool, start) as dist :
            dist.dist += dist.dist.T
            logging.info('Start Single linkage clustering')
            slc = linkage(ssd.squareform(dist.dist), method='single')

        index = { s:i for i, s in enumerate(mat.T[0]) }
        descendents = [ [m] for m in mat.T[0] ] + [None for _ in np.arange(mat.shape[0]-1)]
        for idx, c in enumerate(slc.astype(int)) :
            n_id = idx + mat.shape[0]
            d = sorted([int(c[0]), int(c[1])], key=lambda x:descendents[x][0])
            min_id = min(descendents[d[0]])
            descendents[n_id] = descendents[d[0]] + descendents[d[1]]
            for tgt in descendents[d[1]] :
                res[index[tgt], c[2]+1:] = res[index[min_id], c[2]+1:]
    logging.info('Attach genomes onto the tree.')
    with getDistance(mat, 'asyn_dist', pool, start) as dist :
        for id, (r, d) in enumerate(zip(res[start:], dist.dist)):
            if id + start > 0 :
                i = np.argmin(d[:id+start])
                min_d = d[i]
                if r[min_d + 1] > res[i, min_d + 1]:
                    r[min_d + 1:] = res[i, min_d + 1:]
    pool.close()
    res.T[0] = mat.T[0]
    np.savez_compressed(cluster_file, hierCC=res)

    with gzip.open(params.output + '.hierCC.gz', 'wt') as fout:
        fout.write('#ST_id\t{0}\n'.format('\t'.join(['HC' + str(id) for id in np.arange(n_loci+1)])))
        for r in res[np.argsort(res.T[0])]:
            fout.write('\t'.join([str(rr) for rr in r]) + '\n')

    logging.info('NUMPY clustering result (for incremental hierCC): {0}.npz'.format(params.output))
    logging.info('TEXT  clustering result (for visual inspection): {0}.hierCC.gz'.format(params.output))


if __name__ == '__main__':
    hierCC(sys.argv[1:])
