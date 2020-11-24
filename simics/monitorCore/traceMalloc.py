from simics import *
class TraceMalloc():
    def __init__(self, ida_funs, context_manager, mem_utils, task_utils, cpu, cell, lgr):
        self.ida_funs = ida_funs
        self.cell = cell
        self.cpu = cpu
        self.context_manager = context_manager
        self.mem_utils = mem_utils
        self.task_utils = task_utils
        self.lgr = lgr
        self.malloc_hap = None
        self.malloc_hap_ret = None
        self.malloc_list = []
        self.setBreaks()

    class MallocRec():
        def __init__(self, pid, size):
            self.pid = pid
            self.size = size
            self.addr = None

    def stopTrace(self):
        if self.malloc_hap is not None:
            self.context_manager.genDeleteHap(self.malloc_hap)
            self.malloc_hap = None
        if self.malloc_hap_ret is not None:
            self.context_manager.genDeleteHap(self.malloc_hap_ret)
            self.malloc_hap_ret = None

    def setBreaks(self):
        if self.ida_funs is not None:
            malloc_fun_addr, end = self.ida_funs.getAddr('malloc')
            if malloc_fun_addr is not None:
                malloc_break = self.context_manager.genBreakpoint(self.cell, Sim_Break_Linear, Sim_Access_Execute, malloc_fun_addr, 1, 0)
                self.malloc_hap = self.context_manager.genHapIndex("Core_Breakpoint_Memop", self.mallocHap, None, malloc_break, 'malloc')

            else:
                self.lgr.error('TraceMalloc, address of malloc not found in idaFuns')

    def mallocHap(self, dumb, context, break_num, memory):
        if self.malloc_hap is not None:
            cpu, comm, pid = self.task_utils.curProc() 
            self.lgr.debug('TraceMalloc mallocHap pid:%d' % pid)
            if cpu.architecture == 'arm':
                size = self.mem_utils.getRegValue(self.cpu, 'r0') 
                self.lgr.debug('malloc size %d' % size)
                malloc_rec = self.MallocRec(pid, size)
                lr = self.mem_utils.getRegValue(self.cpu, 'lr') 
                malloc_ret_break = self.context_manager.genBreakpoint(self.cell, Sim_Break_Linear, Sim_Access_Execute, lr, 1, 0)
                self.malloc_hap_ret = self.context_manager.genHapIndex("Core_Breakpoint_Memop", self.mallocEndHap, malloc_rec, malloc_ret_break, 'malloc_end')

    def mallocEndHap(self, malloc_rec, context, break_num, memory):
        if self.malloc_hap_ret is not None:
            cpu, comm, pid = self.task_utils.curProc() 
            self.lgr.debug('TraceMalloc mallocEndHap pid:%d' % pid)
            if cpu.architecture == 'arm':
                addr = self.mem_utils.getRegValue(self.cpu, 'r0') 
                self.lgr.debug('malloc addr 0x%x' % addr)
                malloc_rec.addr = addr
                self.malloc_list.append(malloc_rec)
                self.context_manager.genDeleteHap(self.malloc_hap_ret)
                self.malloc_hap_ret = None

    def showList(self):
        for rec in self.malloc_list:
            print('%4d \t0x%x\t%d' % (rec.pid, rec.addr, rec.size))
