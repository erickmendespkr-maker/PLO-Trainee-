"""Separate desktop launcher for the integrated offline video candidate."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import webbrowser
from plo5_beta_desktop import check as base_check, ROOT
from plo5_pre_gto_context import need
from plo5_selective_review import STREETS, street_filter


def check():
    r=base_check()
    for n in ('cv2','numpy'):
        try:__import__(n);r['checks'][n]=True
        except ImportError:r['checks'][n]=False
    r['ready_for_integrated_candidate']=r['ready_for_candidate_scan'] and all(r['checks'][n] for n in ('cv2','numpy'))
    return r


def command(video,output,streets,tables,*,ppp='',suprema='',session='',start='',seconds='',workers=2,cancel_file=None):
    src=Path(video);out=Path(output);need(src.is_file() and not src.is_symlink() and src.suffix.lower()=='.mp4','Selecione MP4 local.');need(bool(output) and not out.exists() and not out.is_symlink() and out.parent.is_dir(),'Selecione nova pasta de saída.');need(type(workers) is int and 1<=workers<=3,'Trabalhadores inválidos');need(tables and len(set(tables))==len(tables) and all(type(t) is int and 1<=t<=4 for t in tables),'Selecione mesas')
    args=[sys.executable,'-u',str(ROOT/'plo5_integrated_video.py'),str(src),str(out),'--streets',*street_filter(streets),'--tables',*map(str,tables),'--workers',str(workers)]
    need(ppp or suprema,'Selecione ao menos um banco de cartas.')
    for flag,value in (('--ppp',ppp),('--suprema',suprema),('--session',session)):
        if value:
            p=Path(value);need(p.is_file() and not p.is_symlink() and p.suffix.lower()=='.json','JSON inválido');args.extend([flag,str(p)])
    if start!='':s=int(start);need(s>=0,'Início inválido');args.extend(['--start',str(s)])
    if seconds!='':n=int(seconds);need(2<=n<=86400,'Duração inválida');args.extend(['--seconds',str(n)])
    if cancel_file is not None:args.extend(['--cancel-file',str(cancel_file)])
    return args


def gui(smoke=False):
    import tkinter as tk
    from tkinter import ttk,filedialog,messagebox
    app=tk.Tk();app.title('PLO Trainee — candidato integrado');app.geometry('850x700');app.minsize(730,620)
    body=ttk.Frame(app,padding=14);body.pack(fill='both',expand=True);body.columnconfigure(1,weight=1);body.rowconfigure(12,weight=1)
    ttk.Label(body,text='PLO Trainee | Revisão offline PLO5',font=('TkDefaultFont',16,'bold')).grid(row=0,column=0,columnspan=3,sticky='w');ttk.Label(body,text='Reconstrução candidata; estratégia não certificada. DriveHUD fora do beta.',wraplength=780).grid(row=1,column=0,columnspan=3,sticky='w')
    video,output,ppp,suprema,session,start,seconds=[tk.StringVar() for _ in range(7)];workers=tk.IntVar(value=2);status=tk.StringVar(value='Selecione uma sessão encerrada.');selected={s:tk.BooleanVar(value=True) for s in STREETS};tables={t:tk.BooleanVar(value=True) for t in range(1,5)}
    if (ROOT.parent/'calibration'/'ppp_bank.json').is_file():ppp.set(str(ROOT.parent/'calibration'/'ppp_bank.json'))
    def pick(v,k):
        if k=='folder':p=filedialog.askdirectory();p=str(Path(p)/'PLO_Trainee_integrado') if p else ''
        else:p=filedialog.askopenfilename(filetypes=[('MP4','*.mp4')] if k=='video' else [('JSON','*.json')])
        if p:v.set(p)
    for row,label,var,kind in [(2,'Vídeo MP4',video,'video'),(3,'Nova saída',output,'folder'),(4,'Banco PPPoker',ppp,'json'),(5,'Banco Suprema',suprema,'json'),(6,'Sessão anterior (opcional)',session,'json')]:
        ttk.Label(body,text=label).grid(row=row,column=0,sticky='w');ttk.Entry(body,textvariable=var).grid(row=row,column=1,sticky='ew',padx=4,pady=3);ttk.Button(body,text='Selecionar',command=lambda v=var,k=kind:pick(v,k)).grid(row=row,column=2)
    for row,label,items in [(7,'Streets',selected),(8,'Mesas',tables)]:
        ttk.Label(body,text=label).grid(row=row,column=0,sticky='w');f=ttk.Frame(body);f.grid(row=row,column=1,columnspan=2,sticky='w')
        for k,v in items.items():ttk.Checkbutton(f,text=str(k).capitalize(),variable=v).pack(side='left',padx=3)
    ttk.Label(body,text='Intervalo (s) / OCR').grid(row=9,column=0,sticky='w');f=ttk.Frame(body);f.grid(row=9,column=1,columnspan=2,sticky='w');ttk.Label(f,text='Início').pack(side='left');ttk.Entry(f,textvariable=start,width=8).pack(side='left');ttk.Label(f,text='Duração').pack(side='left');ttk.Entry(f,textvariable=seconds,width=8).pack(side='left');ttk.Spinbox(f,from_=1,to=3,textvariable=workers,width=5,state='readonly').pack(side='left',padx=8)
    log=tk.Text(body,height=12,wrap='word');log.grid(row=12,column=0,columnspan=3,sticky='nsew');state={'process':None,'tmp':None,'file':None,'offset':0,'report':None,'buffer':b''}
    def tail():
        file=state['file'];file.seek(state['offset']);raw=file.read(65536);state['offset']=file.tell()
        if raw:
            state['buffer']+=raw;parts=state['buffer'].split(b'\n');state['buffer']=parts.pop()[-65536:]
            for line in parts:
                try:r=json.loads(line).get('progress',{})
                except (ValueError,AttributeError):continue
                if r.get('phase')=='reconstruction':status.set(f"Janelas de reconstrução: {r['completed']}/{r['total']}");bar.stop();bar.configure(mode='determinate',maximum=r['total'],value=r['completed'])
            log.insert('end',raw.decode('utf-8','replace'));log.see('end')
            if int(log.index('end-1c').split('.')[0])>400:log.delete('1.0','200.0')
        return len(raw)
    def poll():
        tail();rc=state['process'].poll()
        if rc is None:app.after(250,poll);return
        while tail():pass
        state['file'].close();state['tmp'].cleanup();state['process']=None;run_btn.configure(state='normal');cancel_btn.configure(state='disabled');bar.stop();ok=rc==0 and state['report'].is_file();open_btn.configure(state='normal' if ok else 'disabled');status.set('Diagnóstico concluído.' if ok else 'Cancelado em checkpoint.' if rc==2 else 'Falha: consulte o log.')
    def cancel():
        if state['process'] is not None:
            (Path(state['tmp'].name)/'cancel').touch();cancel_btn.configure(state='disabled');status.set('Cancelamento solicitado; aguardando etapa segura.')
    def launch():
        if state['process'] is not None:return
        tmp=None;file=None
        try:
            need(check()['ready_for_integrated_candidate'],'Dependências ausentes; execute --check.');tmp=tempfile.TemporaryDirectory();args=command(video.get(),output.get(),[s for s,v in selected.items() if v.get()],[t for t,v in tables.items() if v.get()],ppp=ppp.get(),suprema=suprema.get(),session=session.get(),start=start.get(),seconds=seconds.get(),workers=workers.get(),cancel_file=Path(tmp.name)/'cancel');file=tempfile.TemporaryFile();p=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=file,stderr=subprocess.STDOUT,env=dict(os.environ,OMP_THREAD_LIMIT='1',PYTHONUTF8='1'))
        except (ValueError,OSError,tk.TclError) as e:
            if file:file.close()
            if tmp:tmp.cleanup()
            messagebox.showerror('PLO Trainee',str(e));return
        state.update(process=p,tmp=tmp,file=file,offset=0,buffer=b'',report=Path(output.get())/'index.html');run_btn.configure(state='disabled');cancel_btn.configure(state='normal');open_btn.configure(state='disabled');log.delete('1.0','end');status.set('Reconhecendo vídeo…');bar.configure(mode='indeterminate');bar.start(10);app.after(250,poll)
    run_btn=ttk.Button(body,text='Processar vídeo',command=launch);run_btn.grid(row=10,column=0,sticky='ew');cancel_btn=ttk.Button(body,text='Cancelar',command=cancel,state='disabled');cancel_btn.grid(row=10,column=1);open_btn=ttk.Button(body,text='Abrir relatório',state='disabled',command=lambda:webbrowser.open(state['report'].resolve().as_uri()));open_btn.grid(row=10,column=2)
    ttk.Label(body,textvariable=status).grid(row=11,column=0,columnspan=2,sticky='w');bar=ttk.Progressbar(body,mode='indeterminate');bar.grid(row=11,column=2,sticky='ew')
    def close():
        if state['process'] is not None:cancel();return
        app.destroy()
    app.protocol('WM_DELETE_WINDOW',close)
    if smoke:app.after(300,app.destroy)
    app.mainloop()


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',action='store_true');p.add_argument('--smoke',action='store_true');a=p.parse_args(argv)
    if a.check:r=check();print(json.dumps(r));return 0 if r['ready_for_integrated_candidate'] else 1
    gui(a.smoke);return 0

if __name__=='__main__':raise SystemExit(main())
