import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import queue
import uuid
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from .core import DATA, find_codex, hidden_process, setup_settings, require_subscription, retry_pending, save_settings
from .windows import SingleInstance, enable_dpi, parse_hotkey
from .course_context import reference_folder, reference_file_paths
from .updater import UpdateControl


def runner_command():
    if getattr(sys, 'frozen', False):
        return [str(Path(sys.executable).with_name('Silentanator.exe'))]
    return [str(Path(sys.executable).with_name('pythonw.exe')), '-m', 'silentanator.runner']


class Setup:
    def __init__(self):
        enable_dpi()
        self.settings = setup_settings()
        self.update_draft = DATA / 'setup-update-draft.json'
        self.restored_form = {}
        try:
            saved_draft = json.loads(self.update_draft.read_text(encoding='utf-8'))
            if isinstance(saved_draft, dict):
                self.restored_form = saved_draft
        except (OSError, ValueError):
            pass
        self.root = tk.Tk()
        self.root.title('Silentanator Setup')
        self.root.geometry('740x700')
        self.root.minsize(700, 650)
        style = ttk.Style()
        style.theme_use('vista')
        style.configure('TLabel', font=('Segoe UI', 10))
        style.configure('TButton', padding=7)
        container = ttk.Frame(self.root)
        container.pack(fill='both', expand=True)
        canvas = tk.Canvas(container, highlightthickness=0)
        scroll = ttk.Scrollbar(container, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        frame = ttk.Frame(canvas, padding=24)
        embedded = canvas.create_window((0, 0), window=frame, anchor='nw')
        frame.bind('<Configure>', lambda event: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda event: canvas.itemconfigure(embedded, width=event.width))
        frame.columnconfigure(1, weight=1)
        header = ttk.Frame(frame)
        header.grid(row=0, column=0, columnspan=3, sticky='ew')
        ttk.Label(header, text='Questions → study notes', font=('Segoe UI', 20, 'bold')).pack(side='left')
        self.updater = UpdateControl(self.root, header, self.request_update, restart_setup=True)
        self.updater.frame.pack(side='right', padx=(8, 0))
        ttk.Label(frame, text='Capture on demand. Solve through your ChatGPT-signed-in Codex CLI.').grid(row=1, column=0, columnspan=3, sticky='w', pady=(4, 20))
        self.vars = {}
        fields = [('output', 'Word file (create or add to)'), ('codex', 'Codex executable (auto if blank)'),
                  ('model', 'Model (Codex default if blank)'), ('capture', 'Capture hotkey'),
                  ('toggle', 'Show/hide activity hotkey'), ('quit', 'Exit hotkey'),
                  ('text', 'Show/hide text box hotkey')]
        for row, (key, label) in enumerate(fields, 2):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky='w', padx=(0, 12), pady=7)
            var = self.vars[key] = tk.StringVar(value=self.restored_form.get(key, self.settings[key]))
            ttk.Entry(frame, textvariable=var).grid(row=row, column=1, sticky='ew', pady=7)
            if key == 'output':
                output_buttons = ttk.Frame(frame)
                output_buttons.grid(row=row, column=2, padx=(8, 0))
                ttk.Button(output_buttons, text='Use existing…', command=self.existing_notes).pack(side='left')
                ttk.Button(output_buttons, text='New…', command=lambda: self.browse('output')).pack(side='left', padx=(4, 0))
            elif key == 'codex':
                ttk.Button(frame, text='Browse', command=lambda k=key: self.browse(k)).grid(row=row, column=2, padx=(8, 0))
        self.vars['scope'] = tk.StringVar(value=self.restored_form.get('scope', self.settings['scope']))
        ttk.Label(frame, text='Capture area').grid(row=9, column=0, sticky='w', pady=7)
        ttk.Combobox(frame, values=['active', 'primary'], state='readonly', textvariable=self.vars['scope']).grid(row=9, column=1, sticky='ew')
        ttk.Label(frame, text='active = foreground window; primary = main monitor').grid(row=10, column=1, columnspan=2, sticky='w')
        for row, key, label in [(11, 'silent', 'Start silent (keep activity window hidden)'),
                                (12, 'cues', 'Show brief notifications when live activity is visible'),
                                (13, 'batch_hotkeys', 'Enable Ctrl+2…9 screenshot batch hotkeys')]:
            self.vars[key] = tk.BooleanVar(value=self.restored_form.get(key, self.settings[key]))
            ttk.Checkbutton(frame, text=label, variable=self.vars[key]).grid(row=row, column=0, columnspan=3, sticky='w', pady=7)
        ttk.Label(frame, text='The corner dot is always on: green ready, amber working, red error.\nThe text-box hotkey opens just your question; capture includes that text.\nCtrl+2…9 chooses a count; then use the capture hotkey for every picture.\nExisting Word notes are preserved; a backup is made before each update.\nScreenshots and typed questions are stored in your local session.', justify='left').grid(row=14, column=0, columnspan=3, sticky='w', pady=12)
        buttons = ttk.Frame(frame)
        buttons.grid(row=15, column=0, columnspan=3, sticky='ew', pady=8)
        for label, command in [('Check connection', self.check), ('Retry saved notes', self.retry),
                               ('Save', self.save), ('Save & run', self.start)]:
            ttk.Button(buttons, text=label, command=command).pack(side='left', padx=(0, 8))
        links = ttk.Frame(frame)
        links.grid(row=16, column=0, columnspan=3, sticky='w')
        ttk.Button(links, text='Sign in to Codex', command=self.sign_in).pack(side='left', padx=(0, 8))
        ttk.Button(links, text='Open notes folder', command=self.open_folder).pack(side='left')
        ttk.Button(links, text='Show last status', command=self.show_status).pack(side='left', padx=8)
        course_frame = ttk.LabelFrame(frame, text='Reference documents (optional)', padding=8)
        course_frame.grid(row=17, column=0, columnspan=3, sticky='ew', pady=(8, 0))
        course_frame.columnconfigure(0, weight=1)
        ttk.Label(course_frame, text='Reference folder (includes subfolders)').grid(row=0, column=0, sticky='w')
        self.vars['reference_folder'] = tk.StringVar(value=self.restored_form.get('reference_folder', self.settings.get('reference_folder', '')))
        ttk.Entry(course_frame, textvariable=self.vars['reference_folder']).grid(row=1, column=0, sticky='ew')
        ttk.Button(course_frame, text='Browse…', command=self.browse_reference_folder).grid(row=1, column=1, padx=(8, 0))
        ttk.Label(course_frame, text='Additional reference files (one full path per line)').grid(row=2, column=0, columnspan=2, sticky='w', pady=(6, 0))
        self.reference_files_input = tk.Text(course_frame, height=3, width=55, wrap='none', font=('Segoe UI', 10))
        self.reference_files_input.grid(row=3, column=0, columnspan=2, sticky='ew')
        self.reference_files_input.insert('1.0', '\n'.join(self.restored_form.get('reference_files', self.settings.get('reference_files', []))))
        file_buttons = ttk.Frame(course_frame)
        file_buttons.grid(row=4, column=0, columnspan=2, sticky='w', pady=(5, 0))
        ttk.Button(file_buttons, text='Add files…', command=self.add_reference_files).pack(side='left')
        ttk.Button(file_buttons, text='Clear files', command=lambda: self.reference_files_input.delete('1.0', 'end')).pack(side='left', padx=5)
        ttk.Label(course_frame, text='Folder and files can be used together. Save and restart the runner to apply.\nSelected excerpts are sent to OpenAI; original reference files stay unchanged.',
                  wraplength=640).grid(row=5, column=0, columnspan=2, sticky='w', pady=(5, 0))
        self.status = tk.StringVar(value='Ready to configure. Use the exit hotkey or Task Manager to stop the runner.')
        ttk.Label(frame, textvariable=self.status, wraplength=665, foreground='#395575').grid(row=18, column=0, columnspan=3, sticky='w', pady=(16, 0))
        self.events = queue.Queue()
        self.root.update_idletasks()
        width = max(740, frame.winfo_reqwidth() + 12)
        height = min(max(700, frame.winfo_reqheight() + 12), self.root.winfo_screenheight() - 100)
        self.root.geometry(f'{width}x{height}')
        self.root.minsize(min(width, 740), min(height, 650))
        self.root.after(100, self.poll)
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        if self.restored_form:
            self.update_draft.unlink(missing_ok=True)

    def browse(self, key):
        if key == 'output':
            result = filedialog.asksaveasfilename(defaultextension='.docx', initialfile='Notes.docx', filetypes=[('Word document', '*.docx')])
        else:
            result = filedialog.askopenfilename(filetypes=[('Codex executable', 'codex.exe')])
        if result:
            self.vars[key].set(result)

    def existing_notes(self):
        result = filedialog.askopenfilename(title='Choose existing Word notes to add to', filetypes=[('Word document', '*.docx')])
        if result:
            self.vars['output'].set(result)

    def browse_reference_folder(self):
        result = filedialog.askdirectory(title='Choose reference folder')
        if result:
            self.vars['reference_folder'].set(result)

    def add_reference_files(self):
        selected = filedialog.askopenfilenames(title='Choose reference files', filetypes=[
            ('Study documents', '*.pdf *.docx *.pptx *.md *.txt *.html *.htm')])
        if selected:
            current = self.reference_files_input.get('1.0', 'end').strip()
            self.reference_files_input.delete('1.0', 'end')
            self.reference_files_input.insert('1.0', '\n'.join([*current.splitlines(), *selected]))

    def values(self):
        values = {k: v.get() for k, v in self.vars.items()}
        if not values['output'].strip() or Path(values['output']).suffix.lower() != '.docx':
            raise ValueError('Choose a Word file ending in .docx.')
        values['output'] = str(Path(values['output']).expanduser().resolve())
        values['reference_folder'] = reference_folder(values['reference_folder']) or ''
        values['reference_files'] = reference_file_paths(self.reference_files_input.get('1.0', 'end').splitlines())
        changed = (values['reference_folder'] != self.settings.get('reference_folder', '') or
                   values['reference_files'] != self.settings.get('reference_files', []))
        values['reference_revision'] = uuid.uuid4().hex if changed else self.settings.get('reference_revision', '')
        parsed = [parse_hotkey(values[k]) for k in ('capture', 'toggle', 'quit', 'text')]
        if len(set(parsed)) != 4:
            raise ValueError('Choose four distinct hotkeys.')
        if values['batch_hotkeys']:
            ctrl_mods = parse_hotkey('Ctrl+2')[0]
            if any(mods == ctrl_mods and (ord('2') <= code <= ord('9') or 0x62 <= code <= 0x69)
                   for mods, code in parsed):
                raise ValueError('Ctrl+2…9 are reserved for batch counts. Choose other action hotkeys or disable batch hotkeys.')
        find_codex(values['codex'])
        return values

    def save(self):
        try:
            values = self.values()
            save_settings(values)
            self.settings = values
            self.status.set('Settings saved. Restart a running solver to apply changes.')
            return True
        except Exception as exc:
            messagebox.showerror('Setup', str(exc))
            return False

    def start(self):
        if self.save():
            hidden_process(runner_command(), cwd=Path(__file__).resolve().parent.parent,
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.close()

    def request_update(self):
        # Keep incomplete form edits without validating or changing saved configuration.
        draft = {key: value.get() for key, value in self.vars.items()}
        draft['reference_files'] = self.reference_files_input.get('1.0', 'end').strip().splitlines()
        DATA.mkdir(parents=True, exist_ok=True)
        self.update_draft.write_text(json.dumps(draft, ensure_ascii=False), encoding='utf-8')
        self.close()

    def close(self):
        if getattr(self, 'closed', False):
            return
        self.closed = True
        self.updater.close()
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
