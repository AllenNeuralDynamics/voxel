import threading
import numpy as np
from PIL import Image
import customtkinter as ctk


class SimpleGUI:
    def __init__(self, engine, title="Frame Visualizer"):
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        self.root = ctk.CTk()
        self.root.title(title)
        self.root.geometry("1920x1080")

        self.frame_queue = engine.frame_queue
        self.engine = engine
        self._stop_event = False
        self.engine_thread = None
        self.engine_running = False  # Track if the engine is running

        self.metadata_labels = {}
        self.MAX_WIDTH = 1042

        self._create_gui()

    def _create_gui(self):
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        main_frame = ctk.CTkFrame(self.root, corner_radius=10)
        main_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        main_frame.grid_rowconfigure(0, weight=1)
        main_frame.grid_columnconfigure(0, weight=10)
        main_frame.grid_columnconfigure(1, weight=1)

        image_frame = ctk.CTkFrame(main_frame, corner_radius=5)
        image_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        image_frame.grid_rowconfigure(0, weight=10)
        image_frame.grid_columnconfigure(0, weight=1)

        self.image_label = ctk.CTkLabel(image_frame, text="", anchor="center")
        self.image_label.grid(row=0, column=0, sticky="nsew")

        self.metadata_frame = ctk.CTkFrame(main_frame, corner_radius=5, bg_color="transparent")
        self.metadata_frame.grid(row=0, column=1, sticky="nsew")
        self.metadata_frame.grid_rowconfigure(0, weight=0)
        self.metadata_frame.grid_rowconfigure(1, weight=1)
        self.metadata_frame.grid_columnconfigure(0, weight=1)

        self.metadata_title_label = ctk.CTkLabel(
            self.metadata_frame, text="Metadata", font=("monospace", 16, "bold"), bg_color="transparent"
        )
        self.metadata_title_label.grid(row=0, column=0, sticky="ew", padx=5, pady=5)

        self.metadata_content = ctk.CTkFrame(self.metadata_frame, corner_radius=5, bg_color="transparent")
        self.metadata_content.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        self.metadata_content.grid_columnconfigure(0, weight=1)
        self.metadata_frame.grid_rowconfigure(1, weight=10)

        button_frame = ctk.CTkFrame(self.root, corner_radius=5)
        button_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=5)
        button_frame.grid_columnconfigure(0, weight=1)
        button_frame.grid_columnconfigure(1, weight=0)

        self.status_label = ctk.CTkLabel(button_frame, text="Ready", anchor="center")
        self.status_label.grid(row=0, column=0, sticky="ew", padx=5)

        self.toggle_button = ctk.CTkButton(button_frame, text="Start", command=self.toggle_engine)
        self.toggle_button.grid(row=0, column=1, padx=5, sticky="e")

    def _update_metadata(self, metadata: dict) -> None:
        updated_keys = set()
        for key, value in metadata.items():
            if key in self.metadata_labels:
                _, value_label = self.metadata_labels[key]
                value_label.configure(text=str(value))
            else:
                row_index = len(self.metadata_labels)
                row_frame = ctk.CTkFrame(self.metadata_content)
                row_frame.grid(row=row_index, column=0, sticky="new", pady=2)
                row_frame.grid_columnconfigure(0, weight=1)
                row_frame.grid_columnconfigure(1, weight=1)

                key_label = ctk.CTkLabel(row_frame, text=f"{key}:", anchor="w", font=("monospace", 14, "bold"))
                key_label.grid(row=0, column=0, sticky="w", padx=(5, 5))

                value_label = ctk.CTkLabel(row_frame, text=str(value), anchor="e", font=("monospace", 14))
                value_label.grid(row=0, column=1, sticky="w", padx=(5, 5))

                self.metadata_labels[key] = (key_label, value_label)

            updated_keys.add(key)

        # Remove keys not in updated_keys
        keys_to_remove = [k for k in self.metadata_labels if k not in updated_keys]
        for k in keys_to_remove:
            key_label, value_label = self.metadata_labels[k]
            parent_frame = key_label.master
            parent_frame.destroy()
            del self.metadata_labels[k]

    def toggle_engine(self):
        """Toggle engine start/stop state."""
        if not self.engine_running:
            # Start the engine
            self.status_label.configure(text="Starting engine...")
            self.engine_thread = threading.Thread(target=self.engine.run, daemon=True)
            self.engine_thread.start()
            self.engine_running = True
            self.toggle_button.configure(text="Stop")
        else:
            # Stop the engine
            self._stop_event = True
            self.status_label.configure(text="Stopping...")
            self.engine.stop()
            if self.engine_thread is not None:
                self.engine_thread.join(timeout=2)
            self.engine_running = False
            self.toggle_button.configure(text="Start")
            self.status_label.configure(text="Ready")

    def _update_display(self):
        if not self.frame_queue.empty():
            frame, metadata = self.frame_queue.get()

            if frame.dtype != np.uint8:
                frame = (frame * 255).astype(np.uint8)
            img = Image.fromarray(frame)

            original_width, original_height = img.size
            if original_width > self.MAX_WIDTH:
                scale_factor = self.MAX_WIDTH / original_width
                new_width = self.MAX_WIDTH
                new_height = int(original_height * scale_factor)
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

            img_ctk = ctk.CTkImage(light_image=img, dark_image=img, size=(img.width, img.height))
            self.image_label.configure(image=img_ctk, text="")
            self.image_label.image = img_ctk

            self._update_metadata(metadata)

            self.status_label.configure(text=f"Displayed Frame: {metadata.get('Frame idx', 'N/A')}")

        if not self._stop_event:
            self.root.after(100, self._update_display)
        else:
            # Once we stop, reset the state if needed
            self._stop_event = False

    def start(self):
        self._update_display()
        self.root.mainloop()

    def stop(self):
        """Stop visualization and signal engine to stop."""
        if self.engine_running:
            self._stop_event = True
            self.status_label.configure(text="Stopping...")
            self.engine.stop()
            if self.engine_thread is not None:
                self.engine_thread.join(timeout=2)
            self.engine_running = False
            self.toggle_button.configure(text="Start")
            self.status_label.configure(text="Ready")
        self.root.quit()
