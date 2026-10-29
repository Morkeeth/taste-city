"""Rebuild the README figure from published counts; optional dependency: matplotlib."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
ROOT = Path(__file__).resolve().parents[2]
data = json.loads((ROOT / 'benchmark/qloo-vs-frontier-2026-10/data/hard-g1/result-combined-15-questions.json').read_text())
names = {'composer':'Cursor Composer 2.5','deepseek':'DeepSeek V4 Pro','fable':'Claude Fable 5.1','gemini':'Gemini 4 Argon','glm':'GLM 5.3 (Venice)','gpt':'GPT-6.1','grok':'Grok 4.7','kimi':'Kimi K3.1 Pro','minimax':'MiniMax M3 Preview (Venice)','nemotron':'Nemotron 3 Ultra (Venice)','opus':'Claude Opus 5.5','qwen':'Qwen 3.8 Max (Venice)','sonnet':'Claude Sonnet 5.5'}
rows = sorted(data, key=lambda k:data[k]['step0'][0]/data[k]['step0'][1])
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'svg.fonttype':'none'})
fig, ax = plt.subplots(figsize=(13,9),facecolor='white')
for y,key in enumerate(rows):
 row = data[key]; a,b = [100*row[s][0]/row[s][1] for s in ['step0','step1']]
 ax.plot([a,b],[y,y],color='#888888',lw=2,zorder=1)
 ax.scatter([a],[y],s=80,facecolor='white',edgecolor='black',lw=1.8,zorder=2)
 ax.scatter([b],[y],s=80,color='#0047ff',zorder=2)
 ax.text(a-2,y,f"{row['step0'][0]}/{row['step0'][1]}",ha='right',va='center',fontsize=10)
 ax.text(b+2,y,f"{row['step1'][0]}/{row['step1'][1]}",ha='left',va='center',fontsize=10)
ax.set_yticks(range(len(rows)),[names[k] for k in rows]);ax.invert_yaxis();ax.set_xlim(20,100)
ax.set_xlabel('Named places verified within 500 m (%)');ax.set_xticks([20,40,60,80,100]);ax.grid(axis='x',color='#e8e8e8');ax.set_axisbelow(True);ax.tick_params(length=0,pad=9)
for s in ax.spines.values():s.set_visible(False)
fig.suptitle('Does Qloo help models find real places nearby?',x=.03,ha='left',fontsize=22,fontweight='bold')
fig.text(.03,.92,'13 models · 15 questions per model · 10 addresses in 10 cities · two audiences',fontsize=12)
fig.legend(handles=[Line2D([],[],marker='o',color='none',markeredgecolor='black',markerfacecolor='white',label='Audience + question'),Line2D([],[],marker='o',color='none',markerfacecolor='#0047ff',label='Same prompt + Qloo location results')],loc='upper left',bbox_to_anchor=(.02,.91),ncol=2,frameon=False)
fig.text(.03,.065,'Counts are verified / named places. Unequal denominators reflect model output; OpenStreetMap is incomplete.',fontsize=10)
fig.text(.03,.04,'Source: benchmark/qloo-vs-frontier-2026-10/data/hard-g1/result-combined-15-questions.json · 29 Oct 2026',fontsize=9,color='#555555')
fig.subplots_adjust(left=.29,right=.94,top=.81,bottom=.14)
fig.savefig(Path(__file__).with_name('location-benchmark-13.svg'))
fig.savefig(Path(__file__).with_name('location-benchmark-13.png'),dpi=140)
