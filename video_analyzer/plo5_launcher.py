"""Local PLO5 candidate launcher: audited import, review, and environment checks."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import webbrowser

ROOT = Path(__file__).resolve().parent
DB_SHA = 'bddf887d08b9bfaeb55ab55e287b3398c31cf51620dde2ce9986baf7aeddaa9a'


def preflight(equity=None, *, root=ROOT):
    checks = {'python': sys.version_info >= (3, 11), 'pillow': importlib.util.find_spec('PIL') is not None,
              'tkinter': importlib.util.find_spec('tkinter') is not None}
    tools = {}
    for name, flag in [('ffmpeg','-version'), ('ffprobe','-version'), ('tesseract','--version')]:
        try:
            path = shutil.which(name)
            if not path: raise ValueError('not on PATH')
            r = subprocess.run([path,flag],capture_output=True,text=True,timeout=10,check=True)
            tools[name] = {'ok':True,'version':(r.stdout or r.stderr).splitlines()[0]}
        except (OSError, ValueError, IndexError, subprocess.SubprocessError) as exc:
            tools[name] = {'ok':False,'error':str(exc)}
    modules = ('plo5_windows_candidate.py','plo5_review_pipeline.py','plo5_dense_timeline.py','plo5_financial_observations.py','plo5_visual_report.py','plo5_ingest_job.py')
    missing = [n for n in modules if not (Path(root)/n).is_file()]
    equity_status = 'NOT_PROVIDED'
    if equity:
        p=Path(equity)
        if p.is_file() and not p.is_symlink() and p.stat().st_size<=64*1024**2:
            with p.open('rb') as f: equity_status='REVIEWED_BINARY' if hashlib.file_digest(f,'sha256').hexdigest()==DB_SHA else 'UNREVIEWED'
        else:equity_status='MISSING_OR_UNSAFE'
    return {'variant':5,'checks':checks,'tools':tools,'missing_entry_modules':missing,'equity_status':equity_status,
            'visual_preflight_ok':checks['python'] and checks['pillow'] and all(t['ok'] for t in tools.values()) and not missing,
            'full_dependency_graph_verified':False,'windows_verified':False,'mvp_certified':False}


def file_path(value,suffix):
    if not value:raise ValueError('Selecione um arquivo '+suffix)
    p=Path(value)
    if p.suffix.lower()!=suffix or not p.is_file() or p.is_symlink():raise ValueError('Arquivo local inválido: '+str(p))
    return str(p.resolve())


def output_path(value):
    if not value:raise ValueError('Informe uma pasta nova de saída')
    p=Path(value)
    if p.exists() or p.is_symlink() or not p.parent.is_dir():raise ValueError('A saída deve ser uma pasta nova, com pasta pai existente')
    return str(p.resolve())


def command(kind, source, config, output, *, mode='quick',extract=False,study=None,root=ROOT):
    out=output_path(output);root=Path(root)
    if mode not in ('quick','deep'):raise ValueError('Modo inválido')
    if kind=='audit':
        script=root/'plo5_windows_candidate.py';args=['audit',file_path(source,'.mp4'),file_path(config,'.json'),out]
    elif kind=='review':
        script=root/'plo5_review_pipeline.py';args=[file_path(source,'.json'),file_path(config,'.json'),out,'--mode',mode]
        if extract:args.append('--extract')
        if study:args+=['--study',file_path(study,'.json')]
    else:raise ValueError('Operação inválida')
    if not script.is_file():raise ValueError('Módulo ausente: '+script.name)
    return [sys.executable,'-u',str(script),*args],out


def gui():
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    app=tk.Tk();app.title('PLO Trainee — PLO5 | Candidato de revisão offline');app.geometry('820x570')
    panel=ttk.Frame(app,padding=16);panel.pack(fill='both',expand=True);panel.columnconfigure(1,weight=1)
    kind=tk.StringVar(value='audit');mode=tk.StringVar(value='quick');extract=tk.BooleanVar(value=True)
    source=tk.StringVar();config=tk.StringVar();output=tk.StringVar();study=tk.StringVar();status=tk.StringVar(value='Aguardando operação')
    ttk.Label(panel,text='PLO Trainee • revisão offline',font=('TkDefaultFont',16,'bold')).grid(row=0,column=0,columnspan=3,sticky='w')
    ttk.Label(panel,text='Candidato: não confirma automaticamente mãos, perdas ou erros GTO.').grid(row=1,column=0,columnspan=3,sticky='w',pady=5)
    ttk.Combobox(panel,textvariable=kind,values=('audit','review'),state='readonly').grid(row=2,column=1,sticky='ew')
    ttk.Label(panel,text='Operação').grid(row=2,column=0,sticky='w')
    labels=[]
    def browse(var,types):
        p=filedialog.askopenfilename(filetypes=types)
        if p:var.set(p)
    def pick_output():
        p=filedialog.askdirectory()
        if p:output.set(str(Path(p)/('plo5_'+time.strftime('%Y%m%d_%H%M%S'))))
    for i,(label,var) in enumerate([('Vídeo / Job JSON',source),('Layout / Janelas JSON',config),('Pasta nova de saída',output),('Estudo JSON opcional',study)],3):
        ttk.Label(panel,text=label).grid(row=i,column=0,sticky='w',pady=4)
        ttk.Entry(panel,textvariable=var).grid(row=i,column=1,sticky='ew',padx=4)
        action=pick_output if var is output else lambda v=var:browse(v,[('Arquivos MP4 e JSON','*.mp4 *.json'),('Todos','*')])
        ttk.Button(panel,text='Selecionar',command=action).grid(row=i,column=2)
    ttk.Checkbutton(panel,text='Extrair janelas (modo review)',variable=extract).grid(row=7,column=1,sticky='w')
    ttk.Combobox(panel,textvariable=mode,values=('quick','deep'),state='readonly').grid(row=8,column=1,sticky='ew')
    ttk.Label(panel,text='Modo de estudo').grid(row=8,column=0,sticky='w')
    log=tk.Text(panel,height=12,wrap='word');log.grid(row=11,column=0,columnspan=3,sticky='nsew',pady=5);panel.rowconfigure(11,weight=1)
    state={'process':None,'log':None,'result':None}
    def append(text):log.insert('end',text+'\n');log.see('end')
    def poll():
        p=state['process']
        if p is None:return
        code=p.poll()
        if code is None:app.after(400,poll);return
        f=state['log'];f.seek(0);append(f.read().decode('utf-8','replace'));f.close();state['process']=None
        start.configure(state='normal');status.set('Concluído (candidato)' if code==0 else f'Falha (código {code})');open_btn.configure(state='normal' if code==0 else 'disabled')
    def launch():
        try:
            args,out=command(kind.get(),source.get(),config.get(),output.get(),mode=mode.get(),extract=extract.get(),study=study.get() or None)
            f=tempfile.TemporaryFile(mode='w+b')
            try:p=subprocess.Popen(args,stdout=f,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,shell=False)
            except BaseException:f.close();raise
            state.update(process=p,log=f,result=Path(out));start.configure(state='disabled');open_btn.configure(state='disabled');status.set('Processando — aguarde conclusão');append('Iniciando '+kind.get());app.after(400,poll)
        except (ValueError,OSError) as exc:messagebox.showerror('PLO Trainee',str(exc))
    def open_result():
        p=state['result'];target=p/'index.html'
        if not target.is_file():target=p/'media_audit.json'
        if target.is_file():webbrowser.open(target.resolve().as_uri())
        else:messagebox.showinfo('Resultado',str(p))
    def close():
        if state['process'] is not None:messagebox.showinfo('Processando','Aguarde a operação terminar antes de fechar.');return
        app.destroy()
    start=ttk.Button(panel,text='Executar',command=launch);start.grid(row=9,column=0,sticky='ew',pady=8)
    open_btn=ttk.Button(panel,text='Abrir resultado',command=open_result,state='disabled');open_btn.grid(row=9,column=2,sticky='ew')
    ttk.Label(panel,textvariable=status).grid(row=10,column=0,columnspan=3,sticky='w')
    app.protocol('WM_DELETE_WINDOW',close);app.mainloop()


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',action='store_true');p.add_argument('--equity');a=p.parse_args(argv)
    if a.check:
        result=preflight(a.equity);print(json.dumps(result,ensure_ascii=True,indent=2));return 0 if result['visual_preflight_ok'] else 1
    try:gui()
    except (ImportError,RuntimeError) as exc:print(str(exc),file=sys.stderr);return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
