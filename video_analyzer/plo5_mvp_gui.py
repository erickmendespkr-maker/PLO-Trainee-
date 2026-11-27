"""Small offline Tk interface for the validated candidate workflows."""
import sys
import subprocess
import tempfile
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
from plo5_mvp import preflight

ROOT=Path(__file__).resolve().parent

def gui(smoke=False):
    app=tk.Tk();app.title('PLO Trainee — Revisão offline PLO5');app.geometry('780x500');app.minsize(680,420)
    panel=ttk.Frame(app,padding=16);panel.pack(fill='both',expand=True);panel.columnconfigure(1,weight=1);panel.rowconfigure(8,weight=1)
    mode=tk.StringVar(value='video');source=tk.StringVar();output=tk.StringVar();start=tk.StringVar(value='0');seconds=tk.StringVar(value='20');status=tk.StringVar(value='Selecione uma operação offline.');state={'process':None,'log':None,'report':None}
    ttk.Label(panel,text='PLO Trainee | PLO5',font=('TkDefaultFont',18,'bold')).grid(row=0,column=0,columnspan=3,sticky='w')
    ttk.Label(panel,text='Candidato de revisão: vídeo e históricos não confirmados não recebem EV.').grid(row=1,column=0,columnspan=3,sticky='w')
    ttk.Label(panel,text='Modo').grid(row=2,column=0,sticky='w');ttk.Combobox(panel,textvariable=mode,values=('video','history','models'),state='readonly').grid(row=2,column=1,sticky='ew')
    def choose_input():
        p=filedialog.askopenfilename(filetypes=[('Entradas MP4/TXT/JSON','*.mp4 *.txt *.json'),('Todos','*')]);
        if p:source.set(p)
    def choose_output():
        if mode.get()=='video':
            p=filedialog.askdirectory();p=str(Path(p)/'revisao_plo5') if p else ''
        else:p=filedialog.asksaveasfilename(defaultextension='.html',filetypes=[('HTML','*.html')])
        if p:output.set(p)
    for i,label,var,choose in ((3,'Entrada',source,choose_input),(4,'Nova saída',output,choose_output)):
        ttk.Label(panel,text=label).grid(row=i,column=0,sticky='w');ttk.Entry(panel,textvariable=var).grid(row=i,column=1,sticky='ew',padx=4);ttk.Button(panel,text='Selecionar',command=choose).grid(row=i,column=2)
    ttk.Label(panel,text='Início (s) / duração (2–120 s)').grid(row=5,column=0,sticky='w');f=ttk.Frame(panel);f.grid(row=5,column=1,sticky='w');ttk.Entry(f,textvariable=start,width=10).pack(side='left');ttk.Entry(f,textvariable=seconds,width=10).pack(side='left',padx=4)
    log=tk.Text(panel,height=10,wrap='word');log.grid(row=8,column=0,columnspan=3,sticky='nsew')
    def poll():
        p=state['process'];code=p.poll()
        if code is None:app.after(200,poll);return
        f=state['log'];f.seek(0);log.insert('end',f.read().decode('utf-8','replace'));f.close();state['process']=None
        run.configure(state='normal');status.set('Relatório gerado' if code==0 else 'Falha; veja o log');open_btn.configure(state='normal' if code==0 and state['report'].is_file() else 'disabled')
    def launch():
        try:
            kind=mode.get();src=Path(source.get());out=Path(output.get())
            if not src.is_file() or not output.get() or out.exists():raise ValueError('Selecione entrada válida e saída nova.')
            args=[sys.executable,str(ROOT/'plo5_mvp.py'),kind,str(src),str(out)]
            if kind=='video':args+=['--start',str(int(start.get())),'--seconds',str(int(seconds.get()))]
            if kind=='models':
                cache=Path.home()/'.plo_trainee';cache.mkdir(exist_ok=True);args+=['--cache',str(cache/'strategies.sqlite')]
                for flag,name in (('--native','multiway'),('--rank','rank_worker')):
                    exe=ROOT.parent/'native'/ (name+('.exe' if sys.platform=='win32' else ''))
                    if exe.is_file():args.extend((flag,str(exe)))
            f=tempfile.TemporaryFile()
            try:p=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT)
            except BaseException:f.close();raise
            state.update(process=p,log=f,report=out/'index.html' if kind=='video' else out);run.configure(state='disabled');open_btn.configure(state='disabled');status.set('Processando localmente');app.after(200,poll)
        except (ValueError,OSError) as e:messagebox.showerror('PLO Trainee',str(e))
    run=ttk.Button(panel,text='Executar',command=launch);run.grid(row=6,column=0,sticky='ew',pady=8)
    open_btn=ttk.Button(panel,text='Abrir relatório',state='disabled',command=lambda:webbrowser.open(state['report'].resolve().as_uri()));open_btn.grid(row=6,column=2)
    ttk.Button(panel,text='Verificar ambiente',command=lambda:messagebox.showinfo('Ambiente',str(preflight()))).grid(row=6,column=1)
    ttk.Label(panel,textvariable=status).grid(row=7,column=0,columnspan=3,sticky='w')
    def close():
        if state['process'] is not None:messagebox.showinfo('PLO Trainee','Encerre após a operação atual.');return
        app.destroy()
    app.protocol('WM_DELETE_WINDOW',close)
    if smoke:app.after(300,app.destroy)
    app.mainloop()
if __name__=='__main__':gui('--smoke' in sys.argv)
