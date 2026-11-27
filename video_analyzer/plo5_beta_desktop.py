"""Video-only desktop candidate for PLO5 offline review (Tk, Windows/Linux)."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import webbrowser
from plo5_pre_gto_context import need
from plo5_selective_review import STREETS, street_filter

ROOT=Path(__file__).resolve().parent


def check():
    checks={'python_3_11':sys.version_info>=(3,11)}
    for tool in ('ffmpeg','ffprobe','tesseract'):
        checks[tool]=shutil.which(tool) is not None
    for name in ('PIL','tkinter'):
        try:__import__(name);checks[name]=True
        except ImportError:checks[name]=False
    checks['eng']=False
    if checks['tesseract']:
        try:r=subprocess.run(['tesseract','--list-langs'],capture_output=True,text=True,timeout=15,check=True);checks['eng']='eng' in r.stdout.splitlines()
        except (OSError,subprocess.SubprocessError):pass
    checks['rank_worker']=(ROOT.parent/'native'/('rank_worker.exe' if sys.platform=='win32' else 'rank_worker')).is_file()
    checks['cfr']=(ROOT.parent/'native'/('multiway.exe' if sys.platform=='win32' else 'multiway')).is_file()
    return dict(checks=checks,ready_for_candidate_scan=all(v for k,v in checks.items() if k not in ('rank_worker','cfr')),beta_ready=False,windows_certified=False,drivehud_beta=False)


def command(video,output,streets,*,start='0',seconds='',workers=2,ppp='',suprema='',session=''):
    selected=street_filter(streets);src=Path(video);out=Path(output)
    need(src.is_file() and not src.is_symlink() and src.suffix.lower()=='.mp4','Selecione um MP4 local.')
    need(bool(output) and not out.exists() and not out.is_symlink() and out.parent.is_dir(),'Escolha uma nova pasta de saída.')
    need(type(workers) is int and 1<=workers<=3,'Escolha 1–3 trabalhadores.')
    args=[sys.executable,'-u',str(ROOT/'plo5_beta_video.py'),str(src),str(out),'--streets',*selected,'--workers',str(workers)]
    if session:
        p=Path(session);need(p.is_file() and not p.is_symlink() and p.name=='session.json','Escolha o session.json do reconhecimento.');need(start in ('','0') and not seconds,'Sessão existente define o intervalo.')
        args+=['--session',str(p)]
    else:
        s=int(start or '0');need(s>=0,'Início inválido.');args+=['--start',str(s)]
        if seconds:
            n=int(seconds);need(2<=n<=86400,'Duração inválida.');args+=['--seconds',str(n)]
        for flag,value in (('--ppp',ppp),('--suprema',suprema)):
            if value:
                p=Path(value);need(p.is_file() and not p.is_symlink() and p.suffix.lower()=='.json','Banco de cartas inválido.');args+=[flag,str(p)]
    return args


def gui(smoke=False):
    import tkinter as tk
    from tkinter import ttk,filedialog,messagebox
    app=tk.Tk();app.title('PLO Trainee | PLO5 — candidato de vídeo');app.geometry('810x680');app.minsize(720,600)
    body=ttk.Frame(app,padding=14);body.pack(fill='both',expand=True);body.columnconfigure(1,weight=1);body.rowconfigure(12,weight=1)
    video=tk.StringVar();output=tk.StringVar();session=tk.StringVar();start=tk.StringVar(value='0');seconds=tk.StringVar();workers=tk.IntVar(value=2)
    ppp=tk.StringVar(value=str(ROOT.parent/'calibration'/'ppp_bank.json') if (ROOT.parent/'calibration'/'ppp_bank.json').is_file() else '')
    suprema=tk.StringVar();selected={s:tk.BooleanVar(value=True) for s in STREETS};status=tk.StringVar(value='Selecione uma gravação encerrada.');state={'process':None,'file':None,'report':None,'offset':0}
    ttk.Label(body,text='PLO Trainee | PLO5',font=('TkDefaultFont',18,'bold')).grid(row=0,column=0,columnspan=3,sticky='w')
    ttk.Label(body,text='Candidato experimental: reconhecimento e diagnóstico; estratégia ainda não validada.',wraplength=750).grid(row=1,column=0,columnspan=3,sticky='w',pady=(0,8))
    def pick(var,kind):
        if kind=='folder':
            p=filedialog.askdirectory();p=str(Path(p)/'PLO_Trainee_revisao') if p else ''
        else:p=filedialog.askopenfilename(filetypes=[('Vídeo MP4','*.mp4')] if kind=='mp4' else [('JSON','*.json')])
        if p:var.set(p)
    for r,label,var,kind in [(2,'Vídeo MP4',video,'mp4'),(3,'Nova saída',output,'folder'),(4,'Banco PPPoker',ppp,'json'),(5,'Banco Suprema (opcional)',suprema,'json'),(6,'Reutilizar session.json (opcional)',session,'json')]:
        ttk.Label(body,text=label).grid(row=r,column=0,sticky='w');ttk.Entry(body,textvariable=var).grid(row=r,column=1,sticky='ew',padx=4,pady=3);ttk.Button(body,text='Selecionar',command=lambda v=var,k=kind:pick(v,k)).grid(row=r,column=2)
    ttk.Label(body,text='Streets').grid(row=7,column=0,sticky='w');f=ttk.Frame(body);f.grid(row=7,column=1,columnspan=2,sticky='w')
    for s,v in selected.items():ttk.Checkbutton(f,text=s.capitalize(),variable=v).pack(side='left',padx=4)
    ttk.Label(body,text='Intervalo (s); vazio = até o fim').grid(row=8,column=0,sticky='w');f=ttk.Frame(body);f.grid(row=8,column=1,columnspan=2,sticky='w');ttk.Label(f,text='Início').pack(side='left');ttk.Entry(f,textvariable=start,width=8).pack(side='left');ttk.Label(f,text='Duração').pack(side='left',padx=(8,0));ttk.Entry(f,textvariable=seconds,width=8).pack(side='left')
    ttk.Label(body,text='Trabalhadores OCR').grid(row=9,column=0,sticky='w');ttk.Spinbox(body,from_=1,to=3,textvariable=workers,width=6,state='readonly').grid(row=9,column=1,sticky='w')
    log=tk.Text(body,height=10,wrap='word');log.grid(row=12,column=0,columnspan=3,sticky='nsew')
    def tail():
        f=state['file'];f.seek(state['offset']);raw=f.read(65536);state['offset']=f.tell()
        if raw:
            log.insert('end',raw.decode('utf-8','replace'));log.see('end')
            # Bound on-screen log; complete state saved in output JSON.
            if int(log.index('end-1c').split('.')[0])>400:log.delete('1.0','200.0')
        return len(raw)
    def poll():
        p=state['process'];tail();rc=p.poll()
        if rc is None:app.after(250,poll);return
        while tail():pass
        state['file'].close();state['process']=None;run_btn.configure(state='normal');ok=rc==0 and state['report'].is_file();open_btn.configure(state='normal' if ok else 'disabled');status.set('Diagnóstico concluído — beta ainda não validado.' if ok else 'Falha; veja o log.');bar.stop()
    def launch():
        if state['process'] is not None:return
        try:
            need(check()['ready_for_candidate_scan'],'Ambiente incompleto; use Verificar ambiente.')
            args=command(video.get(),output.get(),[s for s,v in selected.items() if v.get()],start=start.get(),seconds=seconds.get(),workers=workers.get(),ppp=ppp.get(),suprema=suprema.get(),session=session.get())
            f=tempfile.TemporaryFile()
            try:p=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT,env=dict(os.environ,OMP_THREAD_LIMIT='1',PYTHONUTF8='1'))
            except BaseException:f.close();raise
            state.update(process=p,file=f,report=Path(output.get())/'index.html',offset=0);run_btn.configure(state='disabled');open_btn.configure(state='disabled');log.delete('1.0','end');status.set('Processando gravação localmente…');bar.start(10);app.after(250,poll)
        except (ValueError,OSError,tk.TclError) as e:messagebox.showerror('PLO Trainee',str(e))
    run_btn=ttk.Button(body,text='Processar vídeo',command=launch);run_btn.grid(row=10,column=0,sticky='ew',pady=8)
    ttk.Button(body,text='Verificar ambiente',command=lambda:messagebox.showinfo('Ambiente',json.dumps(check(),ensure_ascii=False,indent=2))).grid(row=10,column=1)
    open_btn=ttk.Button(body,text='Abrir diagnóstico',state='disabled',command=lambda:webbrowser.open(state['report'].resolve().as_uri()));open_btn.grid(row=10,column=2)
    ttk.Label(body,textvariable=status).grid(row=11,column=0,columnspan=2,sticky='w');bar=ttk.Progressbar(body,mode='indeterminate');bar.grid(row=11,column=2,sticky='ew')
    def close():
        if state['process'] is not None:messagebox.showinfo('PLO Trainee','Aguarde a operação atual terminar.');return
        app.destroy()
    app.protocol('WM_DELETE_WINDOW',close)
    if smoke:app.after(300,app.destroy)
    app.mainloop()


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',action='store_true');p.add_argument('--smoke',action='store_true');a=p.parse_args(argv)
    if a.check:r=check();print(json.dumps(r,ensure_ascii=False));return 0 if r['ready_for_candidate_scan'] else 1
    gui(a.smoke);return 0

if __name__=='__main__':raise SystemExit(main())
