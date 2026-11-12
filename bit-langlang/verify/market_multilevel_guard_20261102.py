"""Post-hoc uncertainty guard: preserve unclassified opposed horizons."""
import json
from pathlib import Path
import pandas as pd
from .market_season_research_20261102 import sha
SRC=Path('data/verify/market-multilevel-20261102-01');OUT=Path('data/verify/market-multilevel-guard-20261102-01');DEF=Path('docs/市场阶段-级别冲突拒判修正-定义-20261102.md')
def guard(season,big,small):
 return ('UNKNOWN','PULLBACK_OR_LATE_UNRESOLVED') if (big,small)==('UP','DOWN') else (season,None)
def main():
 if OUT.exists():raise FileExistsError(OUT)
 files=[DEF,Path(__file__),SRC/'summary.json']+[SRC/f'{n}-weekly.csv' for n in ('main','stress2021')];hashes={str(p):sha(p) for p in files};all_rows={};summary={}
 for name in ('main','stress2021'):
  d=pd.read_csv(SRC/f'{name}-weekly.csv');labels=[guard(r.season,r.big_relation,r.small_relation) for r in d.itertuples(index=False)];d['guard_season']=[x[0] for x in labels];d['guard_reason']=[x[1] if x[1] else r.reason for x,r in zip(labels,d.itertuples(index=False))]
  altered=d.season.ne(d.guard_season);assert (d.loc[altered,'season']=='AUTUMN').all() and ((d.big_relation=='UP')&(d.small_relation=='DOWN')).sum()==int(altered.sum());assert (d[(d.big_relation=='DOWN')&(d.small_relation=='UP')].guard_season=='UNKNOWN').all()
  summary[name]={'points':len(d),'v1_seasons':d.season.value_counts().to_dict(),'guard_seasons':d.guard_season.value_counts().to_dict(),'changed_to_unknown':int(altered.sum()),'unknown_pct':float(d.guard_season.eq('UNKNOWN').mean()*100),'autumn_status':'NOT_IDENTIFIABLE_FROM_FIXED_FEATURES'};all_rows[name]=d
 if any(sha(p)!=h for p,h in hashes.items()):raise ValueError('input modified')
 OUT.mkdir(parents=True)
 for name,d in all_rows.items():d.to_csv(OUT/f'{name}-weekly.csv',index=False)
 (OUT/'summary.json').write_text(json.dumps({'status':'POST_HOC_UNVERIFIED_UNCERTAINTY_GUARD','results':summary,'inputs_sha256':hashes,'limitations':['No independent human or trader reference labels.','Applied after inspecting known case, not unbiased holdout.','No reliable autumn classifier, decisions are not trading signals.']},ensure_ascii=False,indent=2)+'\n');print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
