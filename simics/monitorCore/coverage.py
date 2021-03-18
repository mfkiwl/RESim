import os
import json
import random
import backStop
from simics import *
'''
Manage code coverage tracking, maintaining two hits files per coverage unit (i.e., per full_path)
'''
class Coverage():
    def __init__(self, top, full_path, context_manager, cell, so_map, cpu, lgr):
        self.lgr = lgr
        self.cell = cell
        self.cpu = cpu
        self.top = top
        self.so_map = so_map
        self.context_manager = context_manager
        self.bp_list = []
        self.bb_hap = []
        self.blocks = None
        self.block_total = 0
        self.funs_hit = []
        self.blocks_hit = {}
        self.full_path = full_path
        block_file = self.full_path+'.blocks'
        self.did_cover = False
        self.enabled = False
        self.latest_hit = None
        self.backstop = None
        self.backstop_cycles = None
        self.afl = None
        self.prev_loc = None
        self.map_size = None
        self.trace_bits = None
        self.afl_map = {}
        self.did_exit = 0
        self.hit_count = 0
        self.afl_del_breaks = []
        self.pid = None
        random.seed(12345)
      

    def loadBlocks(self, block_file):
        if os.path.isfile(block_file):
            with open(block_file) as fh:
                self.blocks = json.load(fh)
                self.orig_blocks = json.loads(json.dumps(self.blocks))
                self.funs_total = len(self.blocks)
            self.lgr.debug('coverage loaded from %s' % block_file)
        else:
            self.lgr.debug('Coverage, no blocks at %s' % block_file)

    def stopCover(self, keep_hits=False):
        self.lgr.debug('coverage, stopCover')
        for bp in self.bp_list:
            try:
                SIM_delete_breakpoint(bp)
            except:
                self.lgr.debug('coverage, stopCover bp %d does not exist?' % bp)
        self.bp_list = []
        for hap in self.bb_hap:
            SIM_hap_delete_callback_id('Core_Breakpoint_Memop', hap)
        self.bb_hap = []
        if not keep_hits:
            self.funs_hit = []
            self.blocks_hit = {}

    def cover(self, force_default_context=False):
        self.lgr.debug('coverage: cover')
        self.offset = 0
        block_file = self.full_path+'.blocks'
        if not os.path.isfile(block_file):
            self.lgr.error('coverage: No blocks file at %s' % block_file)
            return
        self.loadBlocks(block_file)         
        so_entry = self.so_map.getSOAddr(self.full_path)
        if so_entry is None:
            self.lgr.error('coverage no SO entry for %s' % self.full_path)
            return
        if so_entry.address is not None:
            if so_entry.locate is not None:
                self.offset = so_entry.locate+so_entry.offset
            #else:
            #    self.offset = so_entry.address
        else:
            self.lgr.debug('coverage: cover no address in so_entry for %s' % self.full_path)
            return
        #self.lgr.debug('cover offset 0x%x' % self.offset)
        if self.blocks is None:
            self.lgr.error('Coverge: No basic blocks defined')
            return
        self.stopCover()
        resim_context = self.context_manager.getRESimContext()
        default_context = self.context_manager.getDefaultContext()
        for fun in self.blocks:
            for block_entry in self.blocks[fun]['blocks']:
                bb = block_entry['start_ea']
                bb_rel = bb + self.offset
                if self.afl or force_default_context:
                    bp = SIM_breakpoint(default_context, Sim_Break_Linear, Sim_Access_Execute, bb_rel, 1, 0)
                else:
                    bp = SIM_breakpoint(resim_context, Sim_Break_Linear, Sim_Access_Execute, bb_rel, 1, Sim_Breakpoint_Temporary)
                if self.afl:
                    rand = random.randrange(0, self.map_size)
                    self.afl_map[bb_rel] = rand
                self.bp_list.append(bp)                 
                #self.lgr.debug('cover break at 0x%x fun 0x%x -- bb: 0x%x offset: 0x%x break num: %d' % (bb_rel, 
                #   int(fun), bb, self.offset, bp))
        self.lgr.debug('coverage generated %d breaks, now set bb_hap first bp: %d  last: %d current_context %s' % (len(self.bp_list), self.bp_list[0], self.bp_list[-1], 
              self.cpu.current_context))
        self.block_total = len(self.bp_list)
        #self.bb_hap = self.context_manager.genHapRange("Core_Breakpoint_Memop", self.bbHap, None, self.bp_list[0], self.bp_list[-1], name='coverage_hap')
        hap = SIM_hap_add_callback_range("Core_Breakpoint_Memop", self.bbHap, None, self.bp_list[0], self.bp_list[-1])
        self.bb_hap.append(hap)

        if self.afl:
            self.context_manager.watchGroupExits()
            self.context_manager.setExitCallback(self.recordExit)

    def getNumBlocks(self):
        return len(self.bp_list)

    def recordExit(self):
        self.did_exit = 1
        self.lgr.debug('coverage record exit of program under test')
        SIM_break_simulation('did exit')
        self.lgr.debug('coverage record exit of did break')

    def watchExits(self):
        self.context_manager.watchGroupExits()

    def getStatus(self):
        return self.did_exit

    def bbHap(self, dumb, third, break_num, memory):
        ''' HAP when a bb is hit '''
        '''
        pid = self.top.getPID()
        if pid != self.pid:
            self.lgr.debug('converage bbHap, not my pid, got %d I am %d' % (pid, self.pid))
        '''
        addr = memory.logical_address
        if addr == 0:
            self.lgr.error('bbHap,  address is zero? phys: 0x%x break_num %d' % (memory.physical_address, break_num))
            return
        if addr in self.afl_del_breaks:
            ''' already 255 hits '''
            return
        #self.lgr.debug('bbHap, len bb_hap %d break_num %d address: 0x%x' % (len(self.bb_hap), break_num, addr))
        if (self.afl or self.context_manager.watchingThis()) and len(self.bb_hap) > 0:
            if not self.afl:
                if addr not in self.blocks_hit:
                    self.blocks_hit[addr] = self.cpu.cycles
                    self.latest_hit = addr
                    addr_str = '%d' % (addr - self.offset)
                    if addr_str in self.blocks:
                        self.funs_hit.append(addr)
                        #self.lgr.debug('bbHap add funs_hit 0x%x' % addr)
                    #self.lgr.debug('bbHap hit 0x%x %s count %d of %d   Functions %d of %d' % (addr, addr_str, 
                    #       len(self.blocks_hit), self.block_total, len(self.funs_hit), len(self.blocks)))
                    if self.backstop_cycles > 0:
                        self.backstop.setFutureCycleAlone(self.backstop_cycles)
            else:
                ''' AFL mode '''
                cur_loc = self.afl_map[addr]
                index = cur_loc ^ self.prev_loc
                #self.lgr.debug('coverage bbHap cur_loc %d, index %d' % (cur_loc, index))
                #self.lgr.debug('coverage bbHap addr 0x%x, offset 0x%x' % (addr, self.offset))
                if self.trace_bits[index] == 0:
                    self.hit_count += 1
                if self.trace_bits[index] == 255:
                    self.afl_del_breaks.append(addr)
                    if False:
                        self.lgr.debug('high hit break_num %d count index %d 0x%x' % (break_num, index, addr))
                        if addr not in self.afl_del_breaks:
                            SIM_delete_breakpoint(break_num)
                            self.afl_del_breaks.append(addr)
                else:
                    self.trace_bits[index] =  self.trace_bits[index]+1
                #self.trace_bits[index] = min(255, self.trace_bits[index]+1)
                self.prev_loc = cur_loc >> 1
                if self.backstop_cycles > 0:
                    self.backstop.setFutureCycleAlone(self.backstop_cycles)
        
    def getTraceBits(self): 
        #self.lgr.debug('hit count is %d' % self.hit_count)
        return self.trace_bits

    def getHitCount(self):
        return self.hit_count;

    def saveHits(self, fname):
        ''' save blocks_hit to named file '''
        save_name = '%s.%s.hits' % (self.full_path, fname)
        with open(save_name, 'w') as outj:
            json.dump(self.blocks_hit, outj)

    def showCoverage(self):
        ''' blocks_hit and funs_hit are populated via the HAP. '''
        cover = (len(self.blocks_hit)*100) / self.block_total 
        print('Hit %d of %d blocks  (%d percent)' % (len(self.blocks_hit), self.block_total, cover))
        print('Hit %d of %d functions' % (len(self.funs_hit), len(self.blocks)))

    def saveCoverage(self, fname = None):
        if not self.enabled:
            return
        self.lgr.debug('saveCoverage for %d functions' % len(self.funs_hit))
        ''' New dictionary for json.   Key is function address as a string '''
        hit_blocks = {}
        ''' funs_hit is list of addresses as integers '''
        ''' new hit_blocks will all be relocated '''
        '''
        for fun in self.funs_hit:
            fun_str = '%d' % fun
            hit_blocks[fun] = []
            self.lgr.debug('saveCoverage add %s (0x%x) to hit_blocks' % (fun_str, fun))
        '''

        ''' Create a list of bb hit per function '''
        ''' blocks_hit addresses are relocated from offset self.offset'''
        for bb in self.blocks_hit:
            ''' Find the function that contains the bb '''
            ''' self.blocks is not relocated '''
            bb_org = bb - self.offset
            got_it = False
            for ofun in self.blocks:
                for entry in self.blocks[ofun]['blocks']:
                    if entry['start_ea'] == bb_org:
                        ''' bb is in ofun '''
                        ofun_val = int(ofun)
                        ofun_rel = ofun_val + self.offset 
                        ofun_str = str(ofun_rel)
                        if ofun_str not in hit_blocks:
                            #self.lgr.debug('saveCoverage fun %s (0x%x) not in hit_blocks add it' % (ofun_str, ofun_rel))
                            hit_blocks[ofun_str] = []
                        hit_blocks[ofun_str].append(bb)       
                        got_it = True
                        break
                if got_it:
                    break
        s = json.dumps(hit_blocks)
        if fname is None:
            save_name = '%s.hits' % self.full_path
        else:
            save_name = '%s.%s.hits' % (self.full_path, fname)
        with open(save_name, 'w') as fh:
            fh.write(s)
            fh.flush()
        self.lgr.debug('coverage saveCoverage to %s' % save_name)


    def restoreAFLBreaks(self):
        ''' leave unused code as cautionary tale re: pom '''
        self.afl_del_breaks = []
        return 


        '''
        resim_context = self.context_manager.getRESimContext()
        bp_start = 0
        default_context = self.context_manager.getDefaultContext()
        for bb in self.afl_del_breaks:
            breakpoint = SIM_breakpoint(default_context, Sim_Break_Linear, Sim_Access_Execute, bb, 1, 0)
            if bp_start == 0:
                bp_start = breakpoint
        if len(self.afl_del_breaks) > 0:
            hap = SIM_hap_add_callback_range("Core_Breakpoint_Memop", self.bbHap, None, bp_start, breakpoint)
            self.bb_hap.append(hap)
            if len(self.bb_hap) > 100:
                self.lgr.debug('more than 100 haps')
            self.lgr.debug('coverage restoreAFLBreaks restored %d breaks' % len(self.afl_del_breaks))
            self.afl_del_breaks = []
        '''

            
    def restoreBreaks(self):
        ''' Restore the hits found in self.blocks_hit '''
        resim_context = self.context_manager.getRESimContext()
        tmp_list = []
        prev_break = None
        for bb in self.blocks_hit:
            breakpoint = SIM_breakpoint(resim_context, Sim_Break_Linear, Sim_Access_Execute, bb, 1, Sim_Breakpoint_Temporary)
            if prev_break is not None and breakpoint != (prev_break+1):
                #self.lgr.debug('coverage restoreBreaks discontinuous first bb bp is %d last %d' % (tmp_list[0], tmp_list[-1]))
                hap = SIM_hap_add_callback_range("Core_Breakpoint_Memop", self.bbHap, None, tmp_list[0], tmp_list[-1])
                tmp_list = []
                self.bb_hap.append(hap)

            tmp_list.append(breakpoint)
            #self.lgr.debug('coverage restoreBreaks bb 0x%x break num %d' % (bb, breakpoint))
            ''' so it will be deleted '''
            self.bp_list.append(bb)
            prev_break = breakpoint    
        self.lgr.debug('coverage restoreBreaks restored %d breaks' % len(tmp_list))
        if len(tmp_list) > 0:
            self.lgr.debug('coverage restoreBreaks first bb bp is %d last %d' % (tmp_list[0], tmp_list[-1]))
            hap = SIM_hap_add_callback_range("Core_Breakpoint_Memop", self.bbHap, None, tmp_list[0], tmp_list[-1])
            self.bb_hap.append(hap)

    def mergeCover(self):
        all_name = '%s.all.hits' % (self.full_path)
        self.lgr.debug('cover mergeCover into %s' % all_name)
        all_json = {}
        if os.path.isfile(all_name):
            fh = open(all_name, 'r')
            try:
                all_json = json.load(fh)
            except:
                pass
            fh.close()
        last_name = '%s.hits' % self.full_path
        if not os.path.isfile(last_name):
            self.lgr.debug('coverage mergeCover failed to find recent hits file at %s' % last_name)
            return
        with open(last_name) as fh:
            last_json = json.load(fh)
        new_hits = 0
        for fun in last_json:
            if fun not in all_json:
                all_json[fun]=[]
            for bb in last_json[fun]:
                if bb not in all_json[fun]:
                    all_json[fun].append(bb)
                    new_hits += 1
        s = json.dumps(all_json)
        with open(all_name, 'w') as fh:
            fh.write(s)
        os.remove(last_name) 
        self.lgr.debug('coverage merge %d new hits, removed %s' % (new_hits, last_name))
        print('Previous data run hit %d new BBs' % new_hits)
 

    def doCoverage(self, force_default_context=False):
        if not self.enabled:
            self.lgr.debug('cover NOT ENABLED')
            return
        ''' Reset coverage and merge last with all '''
        #self.lgr.debug('coverage doCoverage')    
        if not self.did_cover:
            self.cover(force_default_context=force_default_context)
            self.did_cover = True
        else:
            if not self.afl:
                self.restoreBreaks()

        if not self.afl:
            self.mergeCover()
            self.funs_hit = []
            self.blocks_hit = {}
        #self.lgr.debug('coverage doCoverage set backstop')
        if self.backstop_cycles > 0:
            self.backstop.setFutureCycleAlone(self.backstop_cycles)

        if self.afl:
            self.trace_bits.__init__(self.map_size)
            #self.lgr.debug('coverage trace_bits array size %d' % self.map_size)
            self.prev_loc = 0
            self.did_exit = 0
            self.hit_count = 0

    def startDataSessions(self, dumb):
        if not self.enabled:
            return
        ''' all hits until now are IO setup, prior to any data session except we assume
            the very last hit is the bb that first referenced data '''
        self.lgr.debug('coverage startDataSessions')
        if self.latest_hit is not None:
            first_data_cycle = self.blocks_hit[self.latest_hit]
            del self.blocks_hit[self.latest_hit]
            self.saveCoverage(fname = 'pre')
            self.restoreBreaks()
            self.funs_hit = []
            self.blocks_hit = {}
            self.blocks_hit[self.latest_hit] = first_data_cycle
            self.latest_hit = None
        else:
            self.lgr.debug('coverage startDataSession with no previous hits')

    def enableCoverage(self, pid, fname=None, backstop=None, backstop_cycles=None, afl=False):
        self.enabled = True
        self.pid = pid
        if fname is not None:
            self.full_path = fname
        self.lgr.debug('cover enableCoverage fname is %s' % self.full_path)
        self.backstop = backstop
        self.backstop_cycles = backstop_cycles
        self.afl = afl
        if afl:
            map_size_pow2 = 16
            self.map_size = 1 << map_size_pow2
            self.trace_bits = bytearray(self.map_size)

    def disableCoverage(self):
        self.enabled = False

    def difCoverage(self, fname):
        save_name = '%s.%s.hits' % (self.full_path, fname)
        if not os.path.isfile(save_name):
            print('No file named %s' % save_name)
            return
        with open(save_name) as fh:
            jhits = json.load(fh)
            for i in range(len(jhits)):
                if jhits[i] != self.blocks_hit[i]:
                    print('new 0x%x  old 0x%x index: %d' % (self.blocks_hit[i], jhits[i], i))
                    break

    def getCoverageFile(self):
        ''' Intended to let IDA plugin get file without knowing symbolic links '''
        retval = '%s.hits' % self.full_path
        self.lgr.debug('coverage returning file %s' % retval) 
        return retval

    def goToBasicBlock(self, addr):
        retval = None
        if addr in self.blocks_hit:
            dumb=SIM_run_command('pselect %s' % self.cpu.name)
            cmd = 'skip-to cycle = %d ' % self.blocks_hit[addr]
            self.lgr.debug('coverage goToBasicBlock cmd: %s' % cmd)
            dumb=SIM_run_command(cmd)
            #self.lgr.debug('coverage skipped to 0x%x' % self.cpu.cycles)
            retval = self.cpu.cycles
        else:
            self.lgr.debug('coverage goToBasicBlock 0x%x not in blocks_hit' % addr)
        return retval 

    def getBlocksHit(self):
        return self.blocks_hit
