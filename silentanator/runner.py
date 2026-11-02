import json
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime
import os
import time

from .core import DATA, StudySession, clear_session_pending, load_settings, solve, append_notes, save_pending
from .windows import Hotkeys, SingleInstance, capture_bounds, contain_children, enable_dpi, no_activate, show_corner_dot
from .course_context import reference_folder, reference_file_paths


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
        revision = self.settings.get('reference_revision', '')
        if not self.session.restored or (revision and revision != self.session.reference_revision):
            folder = reference_folder(self.settings.get('reference_folder', ''))
            files = reference_file_paths(self.settings.get('reference_files', []))
            if folder != self.session.course or files != self.session.reference_files:
                self.session = StudySession(self.settings['output'], fresh=True, course=folder,
                                            reference_files=files, reference_revision=revision)
            else:
                self.session.reference_revision = revision
                self.session.persist()
        self.job = contain_children()
        enable_dpi()
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title('Silentanator — Live activity')
        self.root.geometry('860x900')
        self.root.minsize(700, 600)
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.busy = False
        self.state = 'ready'
        self.silent = self.settings.get('silent', True)
        self.cues = self.settings['cues']
        hotkeys = [self.settings[k] for k in ('capture', 'toggle', 'quit')]
        self.batch_key_counts = {}
        if self.settings.get('batch_hotkeys', True):
            for count in range(2, 10):
                hotkeys.append(f'Ctrl+{count}')
                self.batch_key_counts[len(hotkeys)] = count
        self.keys = Hotkeys(hotkeys)
        self.dot = tk.Toplevel(self.root)
        self.dot.withdraw()
        self.dot.overrideredirect(True)
        self.dot.attributes('-topmost', True)
        self.dot.configure(bg='#010101')
        self.dot.attributes('-transparentcolor', '#010101')
        self.dot_location = f'10x10+5+{self.root.winfo_screenheight()-15}'
        self.dot.geometry(self.dot_location)
        self.canvas = tk.Canvas(self.dot, width=10, height=10, bg='#010101', highlightthickness=0)
        self.canvas.pack()
        self.circle = self.canvas.create_oval(2, 2, 8, 8, fill='#38b778', outline='')
        self.next_dot_refresh = 0
        self.dot.update_idletasks()
        no_activate(self.dot)
        self.notice = None
        self.build_activity()
        self.set_input_state('normal')
        if self.cues:
            self.flash('Notes ready')
        self.paint()
        record_status('ready')
        self.activity('Ready. Bring a problem window to the foreground and press ' + self.settings['capture'] + '.')
        self.activity(f'Session restored: {len(self.session.images)} image(s). Each capture updates these notes.')
        if self.session.batch_target:
            self.activity(self.batch_message())
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
        self.session_info = tk.StringVar(value=self.session_summary())
        ttk.Label(frame, textvariable=self.session_info).pack(anchor='w', pady=(0, 5))
        course_row = ttk.Frame(frame)
        course_row.pack(fill='x', pady=(0, 8))
        ttk.Label(course_row, text='Reference folder:').pack(side='left', padx=(0, 8))
        self.folder_path = tk.StringVar(value=self.session.course or '')
        self.reference_entry = ttk.Entry(course_row, textvariable=self.folder_path, width=48)
        self.reference_entry.pack(side='left', fill='x', expand=True)
        self.reference_entry.bind('<Return>', self.apply_reference_folder)
        self.reference_entry.bind('<FocusOut>', self.apply_reference_folder)
        ttk.Label(frame, text='Paste a folder path; subfolders are searched too. Press Enter to use it.\nSelected excerpts are sent to OpenAI; changing folders starts a new session.',
                  wraplength=760).pack(anchor='w', pady=(0, 5))
        ttk.Label(frame, text=f'Additional reference files: {len(self.session.reference_files)} (set in Setup)',
                  wraplength=760).pack(anchor='w', pady=(0, 5))
        question_frame = ttk.LabelFrame(frame, text='Type or paste a question', padding=6)
        question_frame.pack(fill='x', pady=(0, 8))
        self.question_input = tk.Text(question_frame, height=3, wrap='word', font=('Segoe UI', 10))
        self.question_input.pack(fill='x')
        if self.session.batch_question:
            self.question_input.insert('1.0', self.session.batch_question)
        self.question_input.bind('<Control-Return>', self.submit_question)
        question_buttons = ttk.Frame(question_frame)
        question_buttons.pack(fill='x', pady=(5, 0))
        self.attached_images = list(self.session.batch_attachments)
        self.attach_button = ttk.Button(question_buttons, text='Attach images…', command=self.attach_images)
        self.attach_button.pack(side='left')
        self.clear_attachments_button = ttk.Button(question_buttons, text='Clear images', command=self.clear_attachments)
        self.clear_attachments_button.pack(side='left', padx=5)
        self.attachment_info = tk.StringVar(value=f'{len(self.attached_images)} images')
        ttk.Label(question_buttons, textvariable=self.attachment_info).pack(side='left')
        self.solve_button = ttk.Button(question_buttons, text='Solve (Ctrl+Enter)', command=self.submit_question)
        self.solve_button.pack(side='right')
        batch_row = ttk.Frame(frame)
        batch_row.pack(fill='x', pady=(0, 6))
        ttk.Label(batch_row, text='Screenshot batch:').pack(side='left')
        self.batch_count = tk.IntVar(value=2)
        self.batch_spin = ttk.Spinbox(batch_row, from_=2, to=99, width=4, textvariable=self.batch_count)
        self.batch_spin.pack(side='left', padx=5)
        self.batch_button = ttk.Button(batch_row, text='Start batch', command=lambda: self.start_batch(self.batch_spin.get(), False))
        self.batch_button.pack(side='left')
        self.cancel_batch_button = ttk.Button(batch_row, text='Cancel batch', command=self.cancel_batch)
        self.cancel_batch_button.pack(side='left', padx=5)
        batch_help = (f'Ctrl+2…9: start that many pictures. {self.settings["capture"]}: capture remaining pictures.'
                      if self.settings.get('batch_hotkeys', True) else
                      f'Count hotkeys are off. Use Start batch, then capture with {self.settings["capture"]}.')
        ttk.Label(frame, text=batch_help + ' Typed text and attached images join the batch.',
                  wraplength=760).pack(anchor='w', pady=(0, 5))
        ttk.Label(frame, textvariable=self.stage, font=('Segoe UI', 11, 'bold'), wraplength=760).pack(anchor='w')
        self.progress = ttk.Progressbar(frame, mode='indeterminate')
        self.progress.pack(fill='x', pady=8)
        panes = self.panels = ttk.Notebook(frame)
        panes.pack(fill='both', expand=True)
        self.log = self.text_panel(panes, 'Activity log', 7)
        self.answer_view = self.text_panel(panes, 'Session notes (equations are formatted in Word)', 10)
        preview_panel = ttk.Frame(panes, padding=6)
        self.preview = ttk.Label(preview_panel, text='The most recent screenshot will appear here.')
        self.preview.pack(fill='both', expand=True)
        panes.add(preview_panel, text='Last screenshot')
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
        panel = ttk.Frame(panes, padding=6)
        view = tk.Text(panel, wrap='word', height=height, font=('Segoe UI', 10), state='disabled')
        scroll = ttk.Scrollbar(panel, command=view.yview)
        view.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        view.pack(fill='both', expand=True)
        panes.add(panel, text=title)
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
        self.panels.select(self.answer_view.master)

    def session_summary(self):
        summary = f'Session: {len(self.session.images)} image(s), {len(self.session.questions)} typed question(s)'
        if self.session.batch_target:
            summary += f' | Batch: {len(self.session.batch_images)}/{self.session.batch_target}'
        return summary

    def attach_images(self):
        if self.busy or self.session.batch_target:
            return
        selected = filedialog.askopenfilenames(title='Attach images, charts, or diagrams', filetypes=[
            ('Images', '*.png *.jpg *.jpeg *.webp *.bmp *.gif')])
        self.attached_images = list(dict.fromkeys([*self.attached_images, *selected]))
        self.attachment_info.set(f'{len(self.attached_images)} image(s)')

    def clear_attachments(self):
        if not self.busy:
            self.attached_images = []
            self.attachment_info.set('0 images')

    def submit_question(self, event=None):
        if self.busy:
            return 'break'
        if self.session.batch_target:
            self.activity('Finish or cancel the screenshot batch before submitting a typed question.')
            return 'break'
        question = self.question_input.get('1.0', 'end').strip()
        if not question and not self.attached_images:
            self.activity('Type a question or attach an image first.')
            return 'break'
        if len(question) > 30000:
            self.activity('Keep a typed question under 30,000 characters; use reference files for longer material.')
            return 'break'
        if not self.apply_reference_folder():
            return 'break'
        self.busy = True
        self.state = 'working'
        self.progress.start(15)
        self.set_input_state('disabled')
        self.paint()
        self.activity('Preparing the typed question…')
        self.panels.select(self.log.master)
        threading.Thread(target=self.work, args=(None, question, list(self.attached_images)), daemon=True).start()
        return 'break'

    def set_input_state(self, state):
        for control in (self.capture_button, self.new_session_button, self.reference_entry,
                        self.solve_button, self.question_input, self.attach_button,
                        self.clear_attachments_button, self.batch_button, self.batch_spin):
            control.configure(state=state)
        if state == 'normal' and self.session.batch_target:
            for control in (self.new_session_button, self.reference_entry, self.solve_button,
                            self.question_input, self.attach_button, self.clear_attachments_button,
                            self.batch_button, self.batch_spin):
                control.configure(state='disabled')
        self.cancel_batch_button.configure(state='normal' if state == 'normal' and self.session.batch_target else 'disabled')

    def batch_message(self):
        return f'Batch: {len(self.session.batch_images)}/{self.session.batch_target} pictures captured. Select the next problem window and press {self.settings["capture"]}. Nothing sends until the batch is complete.'

    def start_batch(self, count, capture_now=True):
        if self.busy:
            self.activity('Wait for the current request to finish.')
            return
        try:
            count = int(count)
            if self.session.batch_target:
                if count == self.session.batch_target:
                    self.capture()
                else:
                    self.activity('Finish or cancel the current batch before changing its count.')
                return
            if not self.apply_reference_folder():
                return
            question = self.question_input.get('1.0', 'end').strip()
            if len(question) > 30000:
                raise ValueError('Keep a typed question under 30,000 characters.')
            self.session.begin_batch(count, question, self.attached_images)
            self.session_info.set(self.session_summary())
            self.set_input_state('normal')
            self.activity(self.batch_message())
            if capture_now:
                self.capture()
        except (ValueError, tk.TclError) as exc:
            self.activity(str(exc))

    def cancel_batch(self):
        if self.busy:
            return
        self.session.cancel_batch()
        self.session_info.set(self.session_summary())
        self.set_input_state('normal')
        self.activity('Batch cancelled. Its pictures were not sent; earlier session notes remain.')

    def new_session(self):
        if self.busy:
            self.activity('Wait for the current capture to finish before starting a new session.')
            return
        if self.session.batch_target:
            self.activity('Finish or cancel the screenshot batch before starting a new session.')
            return False
        try:
            folder = reference_folder(self.folder_path.get())
        except (OSError, ValueError) as exc:
            self.activity(str(exc))
            return False
        self.session = StudySession(self.settings['output'], fresh=True, course=folder,
                                    reference_files=self.session.reference_files,
                                    reference_revision=self.session.reference_revision)
        self.folder_path.set(folder or '')
        self.session_info.set(self.session_summary())
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
        location = f'10x10+5+{self.root.winfo_screenheight()-15}'
        if location != self.dot_location:
            self.dot.geometry(location)
            self.dot_location = location
        show_corner_dot(self.dot)

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
        self.panels.select(self.log.master)
        self.progress.start(15)
        self.root.withdraw()
        if self.notice and self.notice.winfo_exists():
            self.notice.withdraw()
        self.root.update_idletasks()
        self.busy = True
        self.state = 'working'
        self.paint()
        self.set_input_state('disabled')
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

    def work(self, image=None, question=None, attachments=None):
        try:
            record_status('working')
            new_image_count = 0
            if question or attachments:
                if question:
                    self.session.add_question(question)
                path = None
                if attachments:
                    from PIL import Image, ImageOps
                    # Read attachments locally; originals remain untouched.
                    for attachment in attachments:
                        with Image.open(attachment) as source:
                            path = self.session.add_image(ImageOps.exif_transpose(source).convert('RGB'))
                    new_image_count = len(attachments)
                history = self.session.images[:-1] if path else self.session.images
                questions = self.session.questions[:-1] if question else self.session.questions
            elif self.session.batch_target:
                if len(self.session.batch_images) < self.session.batch_target and not self.session.collect_batch_image(image):
                    self.events.put(('batch_wait', self.batch_message()))
                    return
                attachments = list(self.session.batch_attachments)
                path, new_image_count, question = self.session.commit_batch()
                if attachments:
                    from PIL import Image, ImageOps
                    for attachment in attachments:
                        with Image.open(attachment) as source:
                            path = self.session.add_image(ImageOps.exif_transpose(source).convert('RGB'))
                    new_image_count += len(attachments)
                if question:
                    self.session.add_question(question)
                history = self.session.images[:-1]
                questions = self.session.questions[:-1] if question else self.session.questions
            else:
                path = self.session.add_image(image)
                new_image_count = 1
                history = self.session.images[:-1]
                questions = self.session.questions
            self.events.put(('session', None))
            self.events.put(('progress', f'Building on {len(self.session.images)} image(s) in this session…'))
            answer = solve(path, self.settings, self.cancel,
                           on_progress=lambda detail: self.events.put(('progress', detail)),
                           history=history, previous_answer=self.session.answer,
                           course=self.session.course, question=question, question_history=questions,
                           reference_files=self.session.reference_files, new_image_count=new_image_count)
            self.session.remember(answer)
            self.events.put(('answer', answer))
            self.events.put(('progress', 'Saving a recovery copy of the solution…'))
            pending = save_pending(answer, session_id=self.session.id)
            self.events.put(('progress', 'Converting equations and updating ' + self.settings['output'] + '…'))
            append_notes(Path(self.settings['output']), answer, session_id=self.session.id,
                         on_progress=lambda detail: self.events.put(('progress', detail)))
            clear_session_pending(self.session.id)
            if question or attachments:
                self.events.put(('input_sent', None))
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
                elif key in self.batch_key_counts:
                    self.start_batch(self.batch_key_counts[key])
            except Exception as exc:
                self.events.put(('error', str(exc)))
        while not self.events.empty():
            state, detail = self.events.get_nowait()
            if state == 'input_sent':
                self.question_input.configure(state='normal')
                self.question_input.delete('1.0', 'end')
                self.attached_images = []
                self.attachment_info.set('0 images')
                continue
            if state == 'batch_wait':
                self.busy = False
                self.state = 'ready'
                self.progress.stop()
                self.session_info.set(self.session_summary())
                self.set_input_state('normal')
                self.activity(detail)
                record_status('collecting', detail)
                self.paint()
                continue
            if state == 'session':
                self.session_info.set(self.session_summary())
                continue
            if state == 'progress':
                self.activity(detail)
                continue
            if state == 'answer':
                self.show_answer(detail)
                continue
            self.state = state
            self.busy = False
            self.set_input_state('normal')
            self.progress.stop()
            self.activity(('Error: ' if state == 'error' else '') + detail)
            record_status(self.state, detail)
            self.paint()
            self.flash('Notes saved' if self.state == 'ready' else 'Notes error — see Setup')
            if self.state == 'ready':
                self.activity('Notes saved. Opening the Word document…')
                self.open_notes()
        if time.monotonic() >= self.next_dot_refresh:
            self.paint()
            self.next_dot_refresh = time.monotonic() + 0.5
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
