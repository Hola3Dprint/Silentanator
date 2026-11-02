import json
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
import os

from .core import DATA, StudySession, clear_session_pending, load_settings, solve, append_notes, save_pending
from .windows import Hotkeys, SingleInstance, capture_bounds, contain_children, enable_dpi, no_activate
from .course_context import reference_folder


def record_status(state, detail=''):
    DATA.mkdir(parents=True, exist_ok=True)
    temporary = DATA / 'status.tmp'
    temporary.write_text(json.dumps({'state': state, 'detail': detail}), encoding='utf-8')
    temporary.replace(DATA / 'status.json')


class Runner:
    def __init__(self):
        self.settings = load_settings()
        self.instance = SingleInstance()
        self.session = StudySession(self.settings['output'])
        self.job = contain_children()
        enable_dpi()
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title('Silentanator — Live activity')
        self.root.geometry('860x780')
        self.root.minsize(700, 600)
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.busy = False
        self.state = 'ready'
        self.silent = self.settings.get('silent', True)
        self.cues = self.settings['cues']
        self.keys = Hotkeys([self.settings[k] for k in ('capture', 'toggle', 'quit')])
        self.dot = tk.Toplevel(self.root)
        self.dot.withdraw()
        self.dot.overrideredirect(True)
        self.dot.attributes('-topmost', True)
        self.dot.configure(bg='#010101')
        self.dot.attributes('-transparentcolor', '#010101')
        self.dot.geometry(f'10x10+5+{self.root.winfo_screenheight()-15}')
        self.canvas = tk.Canvas(self.dot, width=10, height=10, bg='#010101', highlightthickness=0)
        self.canvas.pack()
        self.circle = self.canvas.create_oval(2, 2, 8, 8, fill='#38b778', outline='')
        self.dot.update_idletasks()
        no_activate(self.dot)
        self.notice = None
        self.build_activity()
        if self.cues:
            self.flash('Notes ready')
        self.paint()
        record_status('ready')
        self.activity('Ready. Bring a problem window to the foreground and press ' + self.settings['capture'] + '.')
        self.activity(f'Session restored: {len(self.session.images)} image(s). Each capture updates these notes.')
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        self.set_silent(self.silent)

    def set_silent(self, silent):
        self.silent = silent
        if silent:
            self.root.withdraw()
            if self.notice and self.notice.winfo_exists():
                self.notice.withdraw()
        else:
            self.root.deiconify()
        self.paint()

    def build_activity(self):
        frame = ttk.Frame(self.root, padding=18)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Live activity', font=('Segoe UI', 20, 'bold')).pack(anchor='w')
        ttk.Label(frame, text=f"Capture: {self.settings['capture']}   •   Show/hide activity: {self.settings['toggle']}   •   Exit: {self.settings['quit']}\nSelect the problem window, then press the capture hotkey. The corner dot always stays on.", wraplength=760).pack(anchor='w', pady=(6, 10))
        self.stage = tk.StringVar(value='Ready')
        self.session_info = tk.StringVar(value=f'Session: {len(self.session.images)} image(s)')
        ttk.Label(frame, textvariable=self.session_info).pack(anchor='w', pady=(0, 5))
        course_row = ttk.Frame(frame)
        course_row.pack(fill='x', pady=(0, 8))
        ttk.Label(course_row, text='Reference folder:').pack(side='left', padx=(0, 8))
        self.folder_path = tk.StringVar(value=self.session.course or '')
        self.reference_entry = ttk.Entry(course_row, textvariable=self.folder_path, width=48)
        self.reference_entry.pack(side='left', fill='x', expand=True)
        self.reference_entry.bind('<Return>', self.apply_reference_folder)
        self.reference_entry.bind('<FocusOut>', self.apply_reference_folder)
        ttk.Label(frame, text='Paste a folder path; subfolders are searched too. Leave blank for screenshot only.\nPress Enter to use it. Selected excerpts are sent to OpenAI; changing folders starts a new session.',
                  wraplength=760).pack(anchor='w', pady=(0, 5))
        ttk.Label(frame, textvariable=self.stage, font=('Segoe UI', 11, 'bold'), wraplength=760).pack(anchor='w')
        self.progress = ttk.Progressbar(frame, mode='indeterminate')
        self.progress.pack(fill='x', pady=8)
        self.preview = ttk.Label(frame, text='The most recent screenshot will appear here.')
        self.preview.pack(anchor='w', pady=6)
        panes = ttk.Panedwindow(frame, orient='vertical')
        panes.pack(fill='both', expand=True)
        self.log = self.text_panel(panes, 'Activity log', 7)
        self.answer_view = self.text_panel(panes, 'Session notes (equations are formatted in Word)', 10)
        if self.session.answer:
            self.show_answer(self.session.answer)
        buttons = ttk.Frame(frame)
        buttons.pack(side='bottom', fill='x', pady=(10, 0))
        ttk.Button(buttons, text='Open notes', command=self.open_notes).pack(side='left')
        self.capture_button = ttk.Button(buttons, text='Capture in 3 seconds', command=self.delayed_capture)
        self.capture_button.pack(side='left', padx=8)
        self.new_session_button = ttk.Button(buttons, text='New session', command=self.new_session)
        self.new_session_button.pack(side='left')
        ttk.Button(buttons, text='Stop and exit', command=self.close).pack(side='right')
        ttk.Label(frame, text='Saving to: ' + self.settings['output'], wraplength=760).pack(side='bottom', anchor='w', pady=(8, 0))
        # Reserve the controls and output label before giving the notes the remaining space.
        panes.pack_forget()
        panes.pack(fill='both', expand=True)

    def text_panel(self, panes, title, height):
        panel = ttk.LabelFrame(panes, text=title, padding=6)
        view = tk.Text(panel, wrap='word', height=height, font=('Segoe UI', 10), state='disabled')
        scroll = ttk.Scrollbar(panel, command=view.yview)
        view.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        view.pack(fill='both', expand=True)
        panes.add(panel, weight=1)
        return view

    def activity(self, detail):
        self.stage.set(detail)
        self.log.configure(state='normal')
        self.log.insert('end', f'{datetime.now():%H:%M:%S}  {detail}\n')
        self.log.see('end')
        self.log.configure(state='disabled')

    def show_answer(self, answer):
        self.answer_view.configure(state='normal')
        self.answer_view.delete('1.0', 'end')
        for section in answer['sections']:
            self.answer_view.insert('end', section['heading'] + '\n\n')
            for block in section['blocks']:
                self.answer_view.insert('end', block['content'] + '\n\n')
        self.answer_view.configure(state='disabled')

    def new_session(self):
        if self.busy:
            self.activity('Wait for the current capture to finish before starting a new session.')
            return
        try:
            folder = reference_folder(self.folder_path.get())
        except (OSError, ValueError) as exc:
            self.activity(str(exc))
            return False
        self.session = StudySession(self.settings['output'], fresh=True, course=folder)
        self.folder_path.set(folder or '')
        self.session_info.set('Session: 0 images')
        self.answer_view.configure(state='normal')
        self.answer_view.delete('1.0', 'end')
        self.answer_view.configure(state='disabled')
        self.preview.configure(image='', text='The most recent screenshot will appear here.')
        self.activity('New session started. Earlier notes remain in the document.')
        return True

    def apply_reference_folder(self, event=None):
        if self.busy:
            return False
        try:
            folder = reference_folder(self.folder_path.get())
        except (OSError, ValueError) as exc:
            self.activity(str(exc))
            return False
        if folder != self.session.course:
            if not self.new_session():
                return False
            self.activity('Reference folder: ' + (folder or 'none (screenshot only)'))
        self.folder_path.set(folder or '')
        return True

    def open_notes(self):
        try:
            path = Path(self.settings['output'])
            if not path.exists():
                raise RuntimeError('No notes file yet. Capture a problem first.')
            os.startfile(path)
        except Exception as exc:
            self.activity(str(exc))

    def paint(self):
        colors = {'ready': '#38b778', 'working': '#e4ae3d', 'error': '#e15759'}
        self.canvas.itemconfigure(self.circle, fill=colors[self.state])
        self.dot.deiconify()
        self.dot.lift()

    def flash(self, text):
        if self.silent or not self.cues:
            return
        if self.notice and self.notice.winfo_exists():
            self.notice.destroy()
        notice = self.notice = tk.Toplevel(self.root)
        notice.withdraw()
        notice.overrideredirect(True)
        notice.attributes('-topmost', True)
        notice.geometry(f'+18+{self.root.winfo_screenheight()-85}')
        tk.Label(notice, text=text, bg='#202733', fg='white', padx=14, pady=9).pack()
        notice.update_idletasks()
        no_activate(notice)
        notice.deiconify()
        self.root.after(800, lambda: notice.destroy() if notice.winfo_exists() else None)

    def capture(self):
        if self.busy:
            self.activity('A request is already running. Waiting for it to finish.')
            return
        if not self.apply_reference_folder():
            return
        # Acquire foreground bounds before hiding our non-activating overlays.
        bounds = capture_bounds(self.settings['scope'])
        from .windows import user
        if self.settings['scope'] == 'active' and user.GetForegroundWindow() == user.GetParent(self.root.winfo_id()):
            self.activity('Select the problem window first, then press ' + self.settings['capture'] + '.')
            return
        self.activity('Capturing screenshot…')
        self.progress.start(15)
        self.root.withdraw()
        if self.notice and self.notice.winfo_exists():
            self.notice.withdraw()
        self.root.update_idletasks()
        self.busy = True
        self.state = 'working'
        self.paint()
        self.capture_button.configure(state='disabled')
        self.new_session_button.configure(state='disabled')
        self.reference_entry.configure(state='disabled')
        self.root.after(100, lambda: self.take_image(bounds))

    def delayed_capture(self):
        if self.busy:
            return
        if not self.apply_reference_folder():
            return
        self.capture_button.configure(state='disabled')
        self.activity('Capture in 3 seconds. Select the problem window now…')
        self.root.iconify()
        def run_capture():
            self.capture_button.configure(state='normal')
            try:
                self.capture()
            except Exception as exc:
                if not self.silent:
                    self.root.deiconify()
                self.events.put(('error', str(exc)))
        self.root.after(3000, run_capture)

    def take_image(self, bounds):
        from PIL import ImageGrab
        try:
            image = ImageGrab.grab(bbox=bounds, all_screens=bounds is not None)
            from PIL import ImageTk
            thumbnail = image.copy()
            thumbnail.thumbnail((740, 160))
            self.preview_image = ImageTk.PhotoImage(thumbnail)
            self.preview.configure(image=self.preview_image, text='')
            self.activity('Screenshot captured. Preparing the request…')
            self.paint()
            threading.Thread(target=self.work, args=(image,), daemon=True).start()
        except Exception as exc:
            self.events.put(('error', str(exc)))
        finally:
            if not self.silent:
                self.root.deiconify()

    def work(self, image):
        try:
            record_status('working')
            path = self.session.add_image(image)
            self.events.put(('session', len(self.session.images)))
            self.events.put(('progress', f'Building on {len(self.session.images)} image(s) in this session…'))
            answer = solve(path, self.settings, self.cancel,
                           on_progress=lambda detail: self.events.put(('progress', detail)),
                           history=self.session.images[:-1], previous_answer=self.session.answer,
                           course=self.session.course)
            self.session.remember(answer)
            self.events.put(('answer', answer))
            self.events.put(('progress', 'Saving a recovery copy of the solution…'))
            pending = save_pending(answer, session_id=self.session.id)
            self.events.put(('progress', 'Converting equations and updating ' + self.settings['output'] + '…'))
            append_notes(Path(self.settings['output']), answer, session_id=self.session.id,
                         on_progress=lambda detail: self.events.put(('progress', detail)))
            clear_session_pending(self.session.id)
            self.events.put(('ready', 'Notes saved'))
        except Exception as exc:
            self.events.put(('error', str(exc)))

    def tick(self):
        for key in self.keys.poll():
            try:
                if key == 1:
                    self.activity('Capture hotkey received.')
                    self.capture()
                elif key == 2:
                    self.set_silent(not self.silent)
                    self.activity('Silent mode on. The corner dot stays visible.' if self.silent else 'Live activity shown.')
                elif key == 3:
                    self.close()
                    return
            except Exception as exc:
                self.events.put(('error', str(exc)))
        while not self.events.empty():
            state, detail = self.events.get_nowait()
            if state == 'session':
                self.session_info.set(f'Session: {detail} image(s)')
                continue
            if state == 'progress':
                self.activity(detail)
                continue
            if state == 'answer':
                self.show_answer(detail)
                continue
            self.state = state
            self.busy = False
            self.capture_button.configure(state='normal')
            self.new_session_button.configure(state='normal')
            self.reference_entry.configure(state='normal')
            self.progress.stop()
            self.activity(('Error: ' if state == 'error' else '') + detail)
            record_status(self.state, detail)
            self.paint()
            self.flash('Notes saved' if self.state == 'ready' else 'Notes error — see Setup')
            if self.state == 'ready':
                self.activity('Notes saved. Opening the Word document…')
                self.open_notes()
        self.root.after(35, self.tick)

    def close(self):
        self.cancel.set()
        self.keys.close()
        self.instance.close()
        record_status('stopped')
        self.root.destroy()

    def run(self):
        self.tick()
        self.root.mainloop()


def main():
    try:
        Runner().run()
    except Exception as exc:
        record_status('error', str(exc))
        messagebox.showerror('Silentanator', str(exc))


if __name__ == '__main__':
    main()
