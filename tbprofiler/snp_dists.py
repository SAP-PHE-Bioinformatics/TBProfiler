import quickle
from pathogenprofiler import cmd_out,debug,infolog
import os
import json
from .output import write_outputs
from copy import copy
import filelock

class variant_set:
    def __init__(self, vcf_file, prefix, exclude_bed, min_cov=10, min_freq=0.8):
        self.vcf_file = vcf_file
        self.prefix = prefix
        self.min_cov = min_cov
        self.min_freq = min_freq
        self.write_set(exclude_bed)
        self.sample_dists = []
    def write_set(self, exclude_bed,af_cutoff=0.8):
        ref_diffs = set()
        missing = set()
        for l in cmd_out(f"bcftools view -V indels -T ^{exclude_bed} {self.vcf_file} | bcftools query -f '%POS[\t%GT:%AD]\n'"):
            if l[0]=="#": continue
            row = l.strip().split()
            pos = int(row[0])
            gt,ad = row[1].split(":")
            if ad==".": # delly
                continue
            if gt==".": 
                missing.add(pos)
                continue
            ad = [int(x) for x in ad.split(",")]
            if sum(ad)<=10:
                missing.add(pos)
                continue
            adf = sorted([float(x/sum(ad)) for x in ad])
            if adf[-1]<af_cutoff:
                missing.add(pos)
                continue
            if gt=="1/1":
                ref_diffs.add(int(pos))
        self.ref_diffs = ref_diffs
        self.missing = missing
        self.filename = self.prefix + ".non_ref.qkl"
        open(self.filename,"wb").write(quickle.dumps((ref_diffs,missing)))
    def get_snp_dist(self, set_file):
        other_diffs,other_missing = quickle.loads(open(set_file,"rb").read())
        pairwise_dists = self.ref_diffs.symmetric_difference(other_diffs)
        pairwise_dists -= self.missing
        pairwise_dists -= other_missing
        return len(pairwise_dists)
    def get_close_samples(self,dir,cutoff=20):
        directory_files = [f for f in os.listdir(dir) if f.endswith(".qkl")]
        for f in directory_files:
            if f==self.filename: continue
            dist = self.get_snp_dist(os.path.join(dir,f))
            self.sample_dists.append({
                "sample":f.replace(".non_ref.qkl",""),
                "distance":dist
            })
        return [x for x in self.sample_dists if x["distance"]<=cutoff]


def run_snp_dists(args,results):
    infolog("\nCalculating SNP distances to look for closely related samples")
    infolog("-------------------------------------------------------------")
    if args.vcf:
        wg_vcf = args.vcf
    else:
        wg_vcf = args.files_prefix + ".vcf.gz"
    var_set = variant_set(wg_vcf,args.files_prefix,exclude_bed=args.conf['bedmask'])
    results["close_samples"] = var_set.get_close_samples(os.path.join(args.dir,"results"),cutoff=args.snp_dist)
    i=0
    for i,s in enumerate(results['close_samples']):
        infolog("Close sample found: %s (%s). Updating result files" % (s['sample'],s['distance']))
        f = os.path.join(args.dir,"results",f"{s['sample']}.results.json")
        lock = filelock.FileLock(f + ".lock")
        with lock:
            data = json.load(open(f))
            data['close_samples'].append({
                "sample":args.prefix,
                "distance":s['distance']
            })
            temp_args = copy(args)
            temp_args.prefix = s['sample']
            write_outputs(temp_args,data,template_file=args.output_template)
    infolog(f"\nSearched across {i+1} samples and found {len(results['close_samples'])} close samples")
    infolog("-------------------------------------------------------------\n")