// Candidate-bound callbacks are supplied by the ordinary task card player.
export function depthLocation(link,row,base,inspection,note){
  const query=new URLSearchParams({time:String(row.time)});
  if(row.pair?.length){query.set('mode','isolate');for(const region of row.pair)query.append('region',region);}
  link.href=base+'player.html?'+query;
  if(!inspection){link.target='_blank';link.rel='noopener';return;}
  link.onclick=event=>{
    event.preventDefault();
    try{
      inspection.onSeek(row.time);
      if(row.pair?.length)inspection.onRegions(row.pair);
    }catch(error){note.append(document.createTextNode(' 定位未完成：'+error.message));}
  };
}
