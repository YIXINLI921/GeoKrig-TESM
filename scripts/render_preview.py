"""Generate README artwork from actual model outputs; optional matplotlib dependency."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, ListedColormap
import numpy as np
from geokrig.demo import demo_data
from geokrig.core import validate_observations, read_corridor, prepare_snapshot, predict, monitoring_candidates

root=Path(__file__).resolve().parents[1]
raw,route=demo_data()
df=validate_observations(raw)
corridor=read_corridor(route)
snap=prepare_snapshot(df,df.timestamp.iloc[-1],corridor,35)
grid=predict(snap,corridor,'settlement_mm')
sites=monitoring_candidates(grid)
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'text.color':'#172b41',
                     'axes.labelcolor':'#617287','xtick.color':'#617287','ytick.color':'#617287'})
fig=plt.figure(figsize=(14,9),facecolor='#f5f7fa')
fig.text(.06,.94,'GEOSPATIAL MONITORING / TRANSPORT EARTHWORKS',fontsize=11,color='#137f77',weight='bold')
fig.text(.06,.885,'GeoKrig-TESM',fontsize=34,weight='bold')
fig.text(.06,.843,'Kriging estimates, uncertainty and threshold screening along an embankment.',fontsize=14,color='#617287')
fig.text(.06,.797,'30 sensors   /   1.16 km corridor   /   3 snapshots   /   GIS-ready exports',fontsize=12)
axes=[fig.add_axes([.1,y,.78,.135],facecolor='#e6eaf0') for y in [.585,.375,.165]]
extent=[0,corridor.line.length,-35,35]
condition=LinearSegmentedColormap.from_list('condition',['#236a8c','#63b5ac','#f2db8c','#d96052'])
uncertainty=LinearSegmentedColormap.from_list('uncertainty',['#d5eeed','#54ada6','#176f78','#183a58'])
for ax,key,cmap,title,unit in zip(axes[:2],['prediction','std_dev'],[condition,uncertainty],
                                 ['01  CONDITION','02  UNCERTAINTY'],['Settlement (mm)','Kriging SD (mm)']):
    arr=grid[key].to_numpy().reshape(13,90)
    im=ax.imshow(arr,origin='lower',extent=extent,aspect='auto',cmap=cmap,interpolation='nearest')
    ax.scatter(snap.chainage_m,snap.offset_m,s=10,c='#172b41',edgecolors='white',linewidths=.3)
    ax.set_title(title,loc='left',fontweight='bold',pad=10,fontsize=11)
    cax=fig.add_axes([.895,ax.get_position().y0,.012,.135])
    cb=fig.colorbar(im,cax=cax); cb.set_label(unit,fontsize=9)
status=grid.screening.map({'Below threshold':0,'Uncertainty overlaps threshold':1,'Threshold exceeded':2,'No estimate':np.nan})
axes[2].imshow(status.to_numpy().reshape(13,90),origin='lower',extent=extent,aspect='auto',
               cmap=ListedColormap(['#2a9d8f','#e9b44c','#d45151']),vmin=0,vmax=2,interpolation='nearest')
axes[2].set_title('03  THRESHOLD SCREENING + MONITORING CANDIDATES',loc='left',fontweight='bold',pad=10,fontsize=11)
for i,r in sites.iterrows():
    axes[2].text(r.chainage_m,r.offset_m,str(i+1),ha='center',va='center',color='white',fontsize=8,weight='bold',
                 bbox={'boxstyle':'circle,pad=.35','facecolor':'#172b41','edgecolor':'white'})
for ax in axes:
    ax.set_ylabel('Offset (m)'); ax.spines[['top','right']].set_visible(False)
    ax.spines[['left','bottom']].set_color('#bdc8d3')
    ax.set_yticks([-25,0,25])
axes[2].set_xlabel('Chainage from route start (m)')
fig.text(.1,.105,'Below threshold',color='#137f77',fontsize=10)
fig.text(.28,.105,'Uncertainty overlaps threshold',color='#a57413',fontsize=10)
fig.text(.57,.105,'Threshold exceeded',color='#bf4343',fontsize=10)
fig.text(.77,.105,'Grey: no estimate',color='#617287',fontsize=10)
fig.text(.06,.045,'SYNTHETIC HIGHWAY DEMO  •  15 AUG 2026  •  Illustrative 18 mm threshold; screening is not a stability assessment.',fontsize=9,color='#617287')
(root/'docs').mkdir(exist_ok=True)
fig.savefig(root/'docs'/'analysis-preview.png',dpi=160,facecolor=fig.get_facecolor())
plt.close(fig)
