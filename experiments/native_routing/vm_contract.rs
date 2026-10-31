// SPDX-License-Identifier: MIT
// Executes real bytecode in the existing VM. All FPGA/host responses below are models.
use chip32_sim::cpu::{CPU,HaltState};
fn main() {
    let args:Vec<String>=std::env::args().collect();
    assert_eq!(args.len(),3,"Usage: vm-contract loader.bin scenario");
    let scenario=&args[2];
    assert!(["success","skip-switch","skip-return","no-input","clock-stuck","wrong-id","reentry-a","reentry-b","reentry-none"].contains(&scenario.as_str()));
    let mut cpu=CPU::load_file(&args[1],None,Some(0)).unwrap();
    let mut addresses=std::collections::BTreeSet::new();
    let (mut active,mut m,mut d,mut time,mut polls,mut core_calls,mut hosts,mut loads,mut steps)=(None,0u32,0u32,0u32,0u32,Vec::new(),Vec::new(),Vec::new(),0usize);
    if scenario.starts_with("reentry-") {active=Some(0);cpu.work_regs[12]=0x504C4142;}
    while matches!(cpu.halt,HaltState::Running) && steps<3_000_000 {
        let pc=cpu.pc;let low=cpu.ram.read_byte(pc);let op=cpu.ram.read_byte(pc+1);
        let x=(low&15) as usize;let y=(low>>4) as usize;
        let (rx,ry)=(cpu.work_regs[x],cpu.work_regs[y]);
        cpu.step();steps+=1;
        if steps%4096==0 {cpu.logs.clear();}
        if matches!(op,0x3A|0x3B) {addresses.insert(rx);}
        match op {
            0x5B=>{
                core_calls.push(rx);
                if active.is_none() || scenario!="skip-switch" && !(scenario=="skip-return" && core_calls.len()>2) {
                    active=Some(rx);m=0;d=0;time=0;polls=0;
                }
            },
            0x5C=>hosts.push(rx),
            0x53=>loads.push(rx),
            0x3A=>match rx {0x60000020=>m=ry,0x60000024=>d=ry,_=>()},
            0x3B=>{
                cpu.work_regs[y]=match rx {
                    0x60000000=>if scenario=="wrong-id" {0} else {match active {Some(0)=>0x504C4100,Some(1)=>0x504C4201,_=>0}},
                    0x60000008=>{if scenario!="clock-stuck"{time+=1000;}time},
                    0x60000014=>{polls+=1;match scenario.as_str(){"reentry-a"=>1,"reentry-b"=>2,"reentry-none"=>0,_=>if scenario!="no-input" && scenario!="clock-stuck" && polls>=3 {2}else{0}}},
                    0x6000000C=>if scenario=="success" && polls>=2 {0x20}else{0},
                    _=>0
                };
            },
            _=>()
        }
    }
    let exit=match cpu.halt {HaltState::Success=>0,HaltState::Failure=>1,_=>2};
    let addresses:Vec<u32>=addresses.into_iter().collect();
    println!("{{\"exit\":{},\"m\":{},\"d\":{},\"steps\":{},\"cores\":{:?},\"hosts\":{:?},\"loads\":{:?},\"pmp_addresses\":{:?},\"model\":true}}",exit,m,d,steps,core_calls,hosts,loads,addresses);
}
