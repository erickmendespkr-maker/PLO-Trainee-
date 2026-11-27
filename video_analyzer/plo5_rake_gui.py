"""Desktop offline river study with user-defined rake profiles and cached solves."""
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from plo5_rake_presets import profile, save, load, apply
from plo5_post_gto_store import solve_cached


def solve_file(source, database, p, iterations=500):
    path=Path(source)
    if path.stat().st_size>4*1024*1024:raise ValueError('Contexto excede 4 MiB')
    c=json.loads(path.read_text(encoding='utf-8'))
    c,fold=apply(c,p)
    return solve_cached(database,c,iterations=iterations,rake_on_fold=fold)


def gui():
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    root=tk.Tk();root.title('PLO Trainee — Rake / River offline');root.geometry('720x610')
    panel=ttk.Frame(root,padding=12);panel.pack(fill='both',expand=True);panel.columnconfigure(1,weight=1)
    home=Path.home()/'.plo_trainee';home.mkdir(exist_ok=True)
    db=str(home/'river.sqlite');profiles=str(home/'rake_profiles.sqlite')
    fields={k:tk.StringVar(value=v) for k,v in [('platform','Personalizado'),('club','Local'),('limit','Estudo'),('percent','0'),('cap','0'),('source',''),('iterations','500')]}
    fold=tk.BooleanVar(value=False)
    ttk.Label(panel,text='River HU • estudo pós-sessão • configurações manuais').grid(row=0,column=0,columnspan=3,sticky='w')
    for i,(k,label) in enumerate([('platform','Plataforma'),('club','Clube'),('limit','Limite'),('percent','Rake (%)'),('cap','Cap (BB)'),('source','Contexto river JSON'),('iterations','Iterações')],1):
        ttk.Label(panel,text=label).grid(row=i,column=0,sticky='w',pady=3)
        ttk.Entry(panel,textvariable=fields[k]).grid(row=i,column=1,sticky='ew',padx=4)
    def browse():
        p=filedialog.askopenfilename(filetypes=[('Contexto JSON','*.json')]);
        if p:fields['source'].set(p)
    ttk.Button(panel,text='Selecionar',command=browse).grid(row=6,column=2)
    ttk.Checkbutton(panel,text='Cobrar rake no fold',variable=fold).grid(row=8,column=1,sticky='w')
    ttk.Label(panel,text='Cap 0 = sem cobrança. Arredondamento para baixo em fichas.').grid(row=9,column=0,columnspan=3,sticky='w')
    def current():return profile(*(fields[k].get() for k in ('platform','club','limit','percent','cap')),fold.get())
    chosen=tk.StringVar();combo=ttk.Combobox(panel,textvariable=chosen,state='readonly');combo.grid(row=10,column=1,sticky='ew')
    loaded=[]
    def refresh():
        loaded[:]=load(profiles);combo['values']=[f"{p['platform']} / {p['club']} / {p['limit']}" for p in loaded];chosen.set('')
    def select(event=None):
        i=combo.current()
        if i<0:return
        p=loaded[i]
        for k,v in [('platform',p['platform']),('club',p['club']),('limit',p['limit']),('percent',str(p['rake_bps']/100)),('cap',p['cap_bb'])]:fields[k].set(v)
        fold.set(p['rake_on_fold'])
    combo.bind('<<ComboboxSelected>>',select)
    def store():
        try:save(profiles,current());refresh()
        except Exception as e:messagebox.showerror('Rake',str(e))
    ttk.Button(panel,text='Salvar perfil',command=store).grid(row=10,column=2)
    ttk.Label(panel,text='Perfis salvos').grid(row=10,column=0,sticky='w');refresh()
    log=tk.Text(panel,height=12,wrap='word');log.grid(row=12,column=0,columnspan=3,sticky='nsew',pady=6);panel.rowconfigure(12,weight=1)
    pool=ThreadPoolExecutor(max_workers=1);state={'future':None}
    def poll():
        f=state['future']
        if not f.done():root.after(100,poll);return
        state['future']=None;run.configure(state='normal')
        try:
            data=f.result();r=data['result'];log.delete('1.0','end');log.insert('end',json.dumps(dict(model_key=data['model_key'],cache_hit=data['cache_hit'],values_bb=r['values_bb'],expected_rake_bb=r['expected_rake_bb'],nashconv_bb=r['nashconv_bb'],root_policy=[p for p in r['policy'] if p['node']==0]),ensure_ascii=False,indent=2))
        except Exception as e:messagebox.showerror('Solver river',str(e))
    def execute():
        try:p=current();n=int(fields['iterations'].get());source=fields['source'].get()
        except ValueError as e:messagebox.showerror('Rake',str(e));return
        if not 1<=n<=50000:messagebox.showerror('Rake','Iterações inválidas');return
        run.configure(state='disabled');state['future']=pool.submit(solve_file,source,db,p,n);root.after(100,poll)
    def close():
        if state['future'] is not None:messagebox.showinfo('Solver','A resolução está em andamento.');return
        pool.shutdown();root.destroy()
    run=ttk.Button(panel,text='Resolver river offline',command=execute);run.grid(row=11,column=1,sticky='ew',pady=5)
    root.protocol('WM_DELETE_WINDOW',close);root.mainloop()


if __name__=='__main__':gui()
