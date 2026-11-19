"""Conservative offline proposals from timestamped table/board observations."""
import math

def propose_hand_intervals(observations, *, max_gap_seconds=15.0, min_samples=2):
    if not isinstance(observations,list) or type(min_samples) is not int or min_samples<2: raise ValueError('invalid observations')
    if type(max_gap_seconds) not in (int,float) or not math.isfinite(max_gap_seconds) or max_gap_seconds<=0: raise ValueError('invalid gap')
    previous=-1.0; per_table={i:[] for i in range(1,5)}
    for obs in observations:
        if not isinstance(obs,dict): raise ValueError('invalid observation')
        t,tables=obs.get('timestamp_seconds'),obs.get('tables')
        if type(t) not in (int,float) or not math.isfinite(t) or t<=previous or t<0 or not isinstance(tables,list): raise ValueError('invalid timestamp or tables')
        previous=t; seen=set()
        for table in tables:
            if not isinstance(table,dict): raise ValueError('invalid table')
            ident,state,confidence=table.get('table_id'),table.get('board_state'),table.get('confidence')
            if type(ident) is not int or ident not in per_table or ident in seen: raise ValueError('invalid table identity')
            if state not in ('unknown','none_visible','flop','turn','river'): raise ValueError('invalid board state')
            if type(confidence) not in (int,float) or not math.isfinite(confidence) or not 0<=confidence<=1: raise ValueError('invalid confidence')
            seen.add(ident); per_table[ident].append((float(t),state,float(confidence)))
    intervals=[]
    for ident,samples in per_table.items():
        current=[]
        def flush():
            if len(current)>=min_samples:
                intervals.append({'table_id':ident,'start_observed_seconds':current[0][0],
                    'end_observed_seconds':current[-1][0],'sample_count':len(current),
                    'minimum_confidence':min(x[2] for x in current),
                    'board_states_observed':list(dict.fromkeys(x[1] for x in current)),
                    'boundaries_verified':False,'hand_verified':False,
                    'interpretation':'visual interval for human review; may span multiple hands'})
        for sample in samples:
            if current and sample[0]-current[-1][0]>max_gap_seconds:
                flush(); current=[]
            if current and current[-1][1]=='river' and sample[1]=='none_visible':
                flush(); current=[]
            current.append(sample)
        flush()
    intervals.sort(key=lambda x:(x['start_observed_seconds'],x['table_id']))
    return {'schema_version':1,'proposals':intervals,'analysis_verified':False,
            'hand_boundaries_verified':False,'observation_count':len(observations)}
