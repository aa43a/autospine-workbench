// Local edit history only; it cannot mutate candidates or review decisions.
export function createEditHistory(limit=100){
  let past=[],future=[];
  const copy=value=>structuredClone(value);
  return {
    record(value){past.push(copy(value));if(past.length>limit)past.shift();future=[];},
    undo(current){if(!past.length)return null;future.push(copy(current));return past.pop();},
    redo(current){if(!future.length)return null;past.push(copy(current));return future.pop();},
    reset(){past=[];future=[];},
    get canUndo(){return past.length>0;},get canRedo(){return future.length>0;},
  };
}
