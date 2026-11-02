import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import queue
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from .core import DATA, find_codex, hidden_process, load_settings, require_subscription, retry_pending, save_settings
from .windows import SingleInstance, enable_dpi, parse_hotkey


def runner_command():
    if getattr(sys, 'frozen', False):
        return [str(Path(sys.executable).with_name('Silentanator.exe'))]
    return [str(Path(sys.executable).with_name('pythonw.exe')), '-m', 'silentanator.runner']


class Setup:
    def __init__(self):
        enable_dpi()
        self.settings = load_settings()
        self.root = tk.Tk()
        self.root.title('Silentanator Setup')
        self.root.geometry('740x700')
        self.root.minsize(700, 650)
        style = ttk.Style()
        style.theme_use('vista')
        style.configure('TLabel', font=('Segoe UI', 10))
        style.configure('TButton', padding=7)
        frame = ttk.Frame(self.root, padding=24)
        frame.pack(fill='both', expand=True)
        frame.columnconfigure(1, weight=1)
        ttk.Label(frame, text='Screenshot → study notes', font=('Segoe UI', 20, 'bold')).grid(row=0, column=0, columnspan=3, sticky='w')
        ttk.Label(frame, text='Capture on demand. Solve through your ChatGPT-signed-in Codex CLI.').grid(row=1, column=0, columnspan=3, sticky='w', pady=(4, 20))
        self.vars = {}
        fields = [('output', 'Word notes file'), ('codex', 'Codex executable (auto if blank)'),
                  ('model', 'Model (Codex default if blank)'), ('capture', 'Capture hotkey'),
                  ('toggle', 'Show/hide activity hotkey'), ('quit', 'Exit hotkey')]
        for row, (key, label) in enumerate(fields, 2):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky='w', padx=(0, 12), pady=7)
            var = self.vars[key] = tk.StringVar(value=self.settings[key])
            ttk.Entry(frame, textvariable=var).grid(row=row, column=1, sticky='ew', pady=7)
            if key in ('output', 'codex'):
                ttk.Button(frame, text='Browse', command=lambda k=key: self.browse(k)).grid(row=row, column=2, padx=(8, 0))
        self.vars['scope'] = tk.StringVar(value=self.settings['scope'])
        ttk.Label(frame, text='Capture area').grid(row=8, column=0, sticky='w', pady=7)
        ttk.Combobox(frame, values=['active', 'primary'], state='readonly', textvariable=self.vars['scope']).grid(row=8, column=1, sticky='ew')
        ttk.Label(frame, text='active = foreground window; primary = main monitor').grid(row=9, column=1, columnspan=2, sticky='w')
        for row, key, label in [(10, 'silent', 'Start silent (keep activity window hidden)'),
                                (11, 'cues', 'Show brief notifications when live activity is visible')]:
            self.vars[key] = tk.BooleanVar(value=self.settings[key])
            ttk.Checkbutton(frame, text=label, variable=self.vars[key]).grid(row=row, column=0, columnspan=3, sticky='w', pady=7)
        ttk.Label(frame, text='The corner dot is always on: green ready, amber working, red error.\nSilent mode has no activity window, taskbar entry, or notifications.\nWord notes still open automatically after saving.\nSession images are stored locally; show activity to start a New session.', justify='left').grid(row=12, column=0, columnspan=3, sticky='w', pady=12)
        buttons = ttk.Frame(frame)
        buttons.grid(row=13, column=0, columnspan=3, sticky='ew', pady=8)
        for label, command in [('Check connection', self.check), ('Retry saved notes', self.retry),
                               ('Save', self.save), ('Save & run', self.start)]:
            ttk.Button(buttons, text=label, command=command).pack(side='left', padx=(0, 8))
        links = ttk.Frame(frame)
        links.grid(row=14, column=0, columnspan=3, sticky='w')
        ttk.Button(links, text='Sign in to Codex', command=self.sign_in).pack(side='left', padx=(0, 8))
        ttk.Button(links, text='Open notes folder', command=self.open_folder).pack(side='left')
        ttk.Button(links, text='Show last status', command=self.show_status).pack(side='left', padx=8)
        course_frame = ttk.LabelFrame(frame, text='Course references', padding=8)
        course_frame.grid(row=15, column=0, columnspan=3, sticky='ew', pady=(8, 0))
        course_frame.columnconfigure(0, weight=1)
        self.vars['courses_root'] = tk.StringVar(value=self.settings['courses_root'])
        ttk.Entry(course_frame, textvariable=self.vars['courses_root']).grid(row=0, column=0, sticky='ew')
        ttk.Button(course_frame, text='Browse', command=self.browse_courses).grid(row=0, column=1, padx=(8, 0))
        ttk.Label(course_frame, text='Choose a course in Live activity (Ctrl+Alt+0) for each session.\nSelected excerpts are sent to OpenAI with the problem; source files stay unchanged.',
                  wraplength=640).grid(row=1, column=0, columnspan=2, sticky='w', pady=(6, 0))
        self.status = tk.StringVar(value='Ready to configure. Use the exit hotkey or Task Manager to stop the runner.')
        ttk.Label(frame, textvariable=self.status, wraplength=665, foreground='#395575').grid(row=16, column=0, columnspan=3, sticky='w', pady=(16, 0))
        self.events = queue.Queue()
        self.root.update_idletasks()
        width = max(740, frame.winfo_reqwidth() + 12)
        height = max(700, frame.winfo_reqheight() + 12)
        self.root.geometry(f'{width}x{height}')
        self.root.minsize(width, height)
        self.root.after(100, self.poll)

    def browse_courses(self):
        result = filedialog.askdirectory(initialdir=self.vars['courses_root'].get(), title='StudyFlow courses folder')
        if result:
            self.vars['courses_root'].set(result)

    def browse(self, key):
        if key == 'output':
            result = filedialog.asksaveasfilename(defaultextension='.docx', initialfile='Notes.docx', filetypes=[('Word document', '*.docx')])
        else:
            result = filedialog.askopenfilename(filetypes=[('Codex executable', 'codex.exe')])
        if result:
            self.vars[key].set(result)

    def values(self):
        values = {k: v.get() for k, v in self.vars.items()}
        if not values['output'].strip() or Path(values['output']).suffix.lower() != '.docx':
            raise ValueError('Choose a Word file ending in .docx.')
        values['output'] = str(Path(values['output']).expanduser().resolve())
        if values['courses_root'].strip() and not Path(values['courses_root']).expanduser().is_dir():
            raise ValueError('Choose an existing folder containing your course folders.')
        values['courses_root'] = str(Path(values['courses_root']).expanduser().resolve()) if values['courses_root'].strip() else ''
        parsed = [parse_hotkey(values[k]) for k in ('capture', 'toggle', 'quit')]
        if len(set(parsed)) != 3:
            raise ValueError('Choose three distinct hotkeys.')
        find_codex(values['codex'])
        return values

    def save(self):
        try:
            save_settings(self.values())
            self.status.set('Settings saved. Restart a running solver to apply changes.')
            return True
        except Exception as exc:
            messagebox.showerror('Setup', str(exc))
            return False

    def start(self):
        if self.save():
            hidden_process(runner_command(), cwd=Path(__file__).resolve().parent.parent,
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.root.destroy()

    def background(self, operation):
        self.status.set('Working…')
        def work():
            try:
                self.events.put(operation())
            except Exception as exc:
                self.events.put(str(exc))
        threading.Thread(target=work, daemon=True).start()

    def check(self):
        configured = self.vars['codex'].get()
        def operation():
            executable = find_codex(configured)
            require_subscription(executable)
            return 'ChatGPT subscription sign-in is ready. Image requests use your Codex allowance.'
        self.background(operation)

    def sign_in(self):
        try:
            subprocess.Popen([find_codex(self.vars['codex'].get()), 'login'],
                             creationflags=subprocess.CREATE_NEW_CONSOLE)
        except Exception as exc:
            messagebox.showerror('Sign in', str(exc))

    def retry(self):
        try:
            path = Path(self.values()['output'])
        except Exception as exc:
            messagebox.showerror('Notes', str(exc))
            return
        def operation():
            try:
                guard = SingleInstance()
            except RuntimeError:
                raise RuntimeError('Stop the background runner before retrying saved notes.')
            try:
                return f'Added {retry_pending(path)} saved response(s).'
            finally:
                guard.close()
        self.background(operation)

    def open_folder(self):
        folder = Path(self.vars['output'].get()).expanduser().resolve().parent
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(folder)

    def show_status(self):
        try:
            value = json.loads((DATA / 'status.json').read_text(encoding='utf-8'))
            self.status.set(value['state'] + ': ' + value.get('detail', ''))
        except FileNotFoundError:
            self.status.set('The runner has not recorded a status yet.')

    def poll(self):
        while not self.events.empty():
            self.status.set(self.events.get_nowait())
        self.root.after(100, self.poll)

    def run(self):
        self.root.mainloop()


def main():
    try:
        Setup().run()
    except Exception as exc:
        messagebox.showerror('Silentanator Setup', str(exc))


if __name__ == '__main__':
    main()
