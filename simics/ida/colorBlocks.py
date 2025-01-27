import json
from collections import OrderedDict 
import os
import idaapi
import ida_graph
import ida_gdl
import ida_nalt
import idc
import gdbProt
import subprocess
import idaversion
'''
Color basic blocks to reflect whether blocks were hit during the most recent data session, or any data session.
'''
new_hit_color = 0x00ff00 
old_hit_color = 0x00ffcc 
not_hit_color = 0x00ffff
pre_hit_color = 0xccff00
def getBB(graph, bb_addr):
    for block in graph:
        if block.start_ea <= bb_addr and block.end_ea > bb_addr:
            return block
    return None

def getBBId(graph, bb):
    bb = getBB(graph, bb)
    if bb is not None:
        return bb.id
    else:
        return None
   

def doColor(latest_hits_file, all_hits_file, pre_hits_file):
    if os.path.isfile(latest_hits_file):
        with open(latest_hits_file) as funs_fh:
            latest_hits_json = json.load(funs_fh)
        #print('loaded blocks from %s, got %d hits' % (latest_hits_file, len(latest_hits_json)))
    else:
        latest_hits_json = {}
    if os.path.isfile(all_hits_file):
        with open(all_hits_file) as funs_fh:
            all_hits_json = json.load(funs_fh)
        #print('loaded blocks from %s, got %d functions' % (all_hits_file, len(all_hits_json)))
    else:
        all_hits_json = {}
    if os.path.isfile(pre_hits_file):
        with open(pre_hits_file) as funs_fh:
            pre_hits_json = json.load(funs_fh)
        #print('loaded blocks from %s, got %d functions' % (pre_hits_file, len(pre_hits_json)))
    else:
        pre_hits_json = {}
    p = idaapi.node_info_t()
    ''' New hits '''
    p.bg_color =  new_hit_color
    num_new = 0
    graph_dict = {}
    offset = 0
    info = idaapi.get_inf_structure()
    if info.is_dll():
        offset = ida_nalt.get_imagebase()

    for bb in latest_hits_json:
        bb = bb + offset
        f = idaapi.get_func(bb)
        if f is None:
            print('Error getting function for bb 0x%x' % bb)
            return
        f_start = f.start_ea
        if f_start not in graph_dict:
            graph_dict[f_start] = ida_gdl.FlowChart(f, flags=ida_gdl.FC_PREDS)
        block = getBB(graph_dict[f_start], bb)
        if block is not None:
            bb_id = block.id
            if bb not in all_hits_json:
                ''' first time bb has been hit in any data session '''
                p.bg_color =  new_hit_color
                ida_graph.set_node_info(f.start_ea, bb_id, p, idaapi.NIF_BG_COLOR | idaapi.NIF_FRAME_COLOR)
                num_new += 1
            elif bb in all_hits_json:
                ''' also hit in earlier data session '''
                p.bg_color =  old_hit_color
                ida_graph.set_node_info(f.start_ea, bb_id, p, idaapi.NIF_BG_COLOR | idaapi.NIF_FRAME_COLOR)
            else:
                print('impossible')
                exit(1)
        else: 
            print('block for 0x%x is None' % bb)

    print('Colored %d hits' % num_new)

    ''' Not hit on recent data session, but hit previously '''
    p.bg_color =  not_hit_color
    for bb in all_hits_json:
        f = idaapi.get_func(bb)
        #print('fun addr 0x%x' % fun_addr)
        if f is None:
            print('unable to get function from addr 0x%x' % bb)
            continue
        if f not in graph_dict:
            graph_dict[f] = ida_gdl.FlowChart(f, flags=ida_gdl.FC_PREDS)
        bb_id = getBBId(graph_dict[f], bb)
        if bb_id is not None:
            if bb not in latest_hits_json:
                ida_graph.set_node_info(f.start_ea, bb_id, p, idaapi.NIF_BG_COLOR | idaapi.NIF_FRAME_COLOR)
                #print('not hit fun 0x%x bb: 0x%x' % (fun_addr, bb))

    ''' Hit prior to start of any data session, i.e., IO setup '''
    p.bg_color =  pre_hit_color
    for bb in pre_hits_json:
        f = idaapi.get_func(bb)
        #print('fun addr 0x%x' % fun_addr)
        if f not in graph_dict:
            graph_dict[f] = ida_gdl.FlowChart(f, flags=ida_gdl.FC_PREDS)
        bb_id = getBBId(graph_dict[f], bb)
        if bb_id is not None:
            if bb not in latest_hits_json and bb not in all_hits_json:
                ida_graph.set_node_info(f.start_ea, bb_id, p, idaapi.NIF_BG_COLOR | idaapi.NIF_FRAME_COLOR)
                #print('not hit fun 0x%x bb: 0x%x' % (fun_addr, bb))

def colorBlocks(in_path=None):
    resim_ida_data = os.getenv('RESIM_IDA_DATA')
    if resim_ida_data is None:
        print('RESIM_IDA_DATA not defined.')
    else:
        #in_path = idaapi.get_root_filename()
        if in_path is None:
            ''' TBD this is broken, argv1 is sometimes other param, e.g., color'''
            in_path = idc.eval_idc("ARGV[1]")
        base = os.path.basename(in_path)
        fname = os.path.join(resim_ida_data, base, base)
        latest_hits_file = fname+'.hits' 
        #print('latest_hits_file is %s' % latest_hits_file)
        if not os.path.isfile(latest_hits_file):
            ida_db_path = os.getenv('IDA_DB_PATH')
            if ida_db_path is not None:
                base = os.path.basename(ida_db_path)
                base = base.rsplit('.',1)[0]
                fname = os.path.join(resim_ida_data, base, base)
                latest_hits_file = fname+'.hits' 
            else:
                print('no latest hits file at %s, and no IDA_DB_PATH env variable defined' % latest_hits_file)
                
            
        if os.path.isfile(latest_hits_file):
            print('Using latest_hits_file is %s' % latest_hits_file)
            all_hits_file = fname+'.all.hits'
            pre_hits_file = fname+'.pre.hits'
            doColor(latest_hits_file, all_hits_file, pre_hits_file)
        else:
            print('no latest hits file at %s' % latest_hits_file)

if __name__ == '__main__':
    fname = idaversion.get_root_file_name()
    colorBlocks(fname)
