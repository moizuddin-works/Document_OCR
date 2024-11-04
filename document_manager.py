import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json
from datetime import datetime
import hashlib
from typing import Dict
import os
import re
from tkinterdnd2 import DND_FILES, TkinterDnD
from doctr.io import DocumentFile
from doctr.models import ocr_predictor
import cv2
import numpy as np

class DocumentManager:
    def __init__(self):
        # Initialize database
        self.init_database()
        
        # Initialize DocTR model
        self.model = ocr_predictor(pretrained=True)
        
        # Create main window
        self.window = TkinterDnD.Tk()
        self.window.title("Document Management System")
        self.window.geometry("1000x600")
        
        # Initialize search variables
        self.search_var = tk.StringVar()
        self.search_var.trace('w', self.on_search_change)
        
        # Create main container
        self.main_container = ttk.Frame(self.window, padding="10")
        self.main_container.pack(fill=tk.BOTH, expand=True)
        
        # Create UI elements
        self.create_ui()

    def init_database(self):
        """Initialize SQLite database and create necessary tables"""
        # First, try to remove the old database file
        try:
            import os
            if os.path.exists('documents.db'):
                os.remove('documents.db')
        except:
            pass
        
        self.conn = sqlite3.connect('documents.db')
        self.cursor = self.conn.cursor()
        
        # Create documents table with only necessary fields
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY,
                raw_text TEXT NOT NULL,
                date_added TIMESTAMP,
                last_modified TIMESTAMP,
                verification_status TEXT
            )
        ''')
        
        # Create audit log table
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER,
                action TEXT,
                timestamp TIMESTAMP,
                user TEXT,
                details TEXT,
                FOREIGN KEY (document_id) REFERENCES documents (id)
            )
        ''')
        
        self.conn.commit()

    def create_ui(self):
        """Create the user interface"""
        # Create notebook for tabs
        self.notebook = ttk.Notebook(self.main_container)
        self.notebook.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Create tabs
        self.scan_tab = ttk.Frame(self.notebook)
        self.documents_tab = ttk.Frame(self.notebook)
        self.search_tab = ttk.Frame(self.notebook)
        self.audit_tab = ttk.Frame(self.notebook)
        
        self.notebook.add(self.scan_tab, text="Scan Document")
        self.notebook.add(self.documents_tab, text="Documents")
        self.notebook.add(self.search_tab, text="Search")
        self.notebook.add(self.audit_tab, text="Audit Log")
        
        # Setup each tab
        self.setup_scan_tab()
        self.setup_documents_tab()
        self.setup_search_tab()
        self.setup_audit_tab()

    def setup_scan_tab(self):
        """Setup the document scanning tab"""
        # Create drag & drop label
        self.drop_label = tk.Label(
            self.scan_tab,
            text="Drag and drop image here\nor",
            bg='lightgray',
            height=10,
            width=40
        )
        self.drop_label.pack(pady=20)
        
        # Bind drag & drop events
        self.drop_label.drop_target_register(DND_FILES)
        self.drop_label.dnd_bind('<<Drop>>', self.handle_drop)
        self.drop_label.bind('<Enter>', self.handle_enter)
        self.drop_label.bind('<Leave>', self.handle_leave)
        
        # Browse button
        self.browse_btn = ttk.Button(
            self.scan_tab,
            text="Browse Files",
            command=self.browse_files
        )
        self.browse_btn.pack(pady=10)
        
        # Preview frame
        self.preview_frame = ttk.LabelFrame(self.scan_tab, text="Extracted Information")
        self.preview_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Result text area
        self.result_text = tk.Text(self.preview_frame, height=10, width=50)
        self.result_text.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)

    def setup_documents_tab(self):
        """Setup the documents management tab"""
        # Create frames
        controls_frame = ttk.Frame(self.documents_tab)
        controls_frame.pack(fill=tk.X, pady=5)
        
        # Add control buttons
        ttk.Button(
            controls_frame,
            text="Delete Selected",
            command=self.delete_selected_document
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            controls_frame,
            text="Edit Selected",
            command=self.edit_selected_document
        ).pack(side=tk.LEFT, padx=5)
        
        # Create treeview for documents
        self.documents_tree = ttk.Treeview(
            self.documents_tab,
            columns=("ID", "Added", "Modified", "Status"),
            show="headings"
        )
        
        # Setup columns
        self.documents_tree.heading("ID", text="ID")
        self.documents_tree.heading("Added", text="Date Added")
        self.documents_tree.heading("Modified", text="Last Modified")
        self.documents_tree.heading("Status", text="Status")
        
        # Add scrollbar
        scrollbar = ttk.Scrollbar(
            self.documents_tab,
            orient=tk.VERTICAL,
            command=self.documents_tree.yview
        )
        self.documents_tree.configure(yscrollcommand=scrollbar.set)
        
        # Pack elements
        self.documents_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Bind double-click event
        self.documents_tree.bind("<Double-1>", self.on_document_double_click)
        
        # Add right-click menu
        self.create_context_menu()
        
        # Load documents
        self.load_documents()

    def create_context_menu(self):
        """Create right-click context menu"""
        self.context_menu = tk.Menu(self.window, tearoff=0)
        self.context_menu.add_command(label="View", command=self.view_selected_document)
        self.context_menu.add_command(label="Edit", command=self.edit_selected_document)
        self.context_menu.add_command(label="Delete", command=self.delete_selected_document)
        
        # Bind right-click event
        self.documents_tree.bind("<Button-3>", self.show_context_menu)

    def show_context_menu(self, event):
        """Show context menu on right-click"""
        try:
            self.documents_tree.selection_set(
                self.documents_tree.identify_row(event.y)
            )
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()

    def delete_selected_document(self):
        """Delete the selected document"""
        selection = self.documents_tree.selection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a document to delete")
            return
        
        if not messagebox.askyesno("Confirm Delete", 
                                  "Are you sure you want to delete this document?"):
            return
        
        try:
            for item in selection:
                doc_id = self.documents_tree.item(item)['values'][0]
                
                # Delete document
                self.cursor.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
                
                # Log deletion
                self.log_action(doc_id, 'DELETE', f'Document {doc_id} deleted from system')
                
            self.conn.commit()
            self.load_documents()  # Refresh display
            messagebox.showinfo("Success", "Document(s) deleted successfully")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to delete document: {str(e)}")

    def edit_selected_document(self):
        """Edit the selected document"""
        selection = self.documents_tree.selection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a document to edit")
            return
        
        item = selection[0]
        doc_id = self.documents_tree.item(item)['values'][0]
        
        # Get current document data
        self.cursor.execute("SELECT raw_text FROM documents WHERE id = ?", (doc_id,))
        doc = self.cursor.fetchone()
        
        if not doc:
            messagebox.showerror("Error", "Document not found")
            return
        
        # Create edit dialog
        dialog = tk.Toplevel(self.window)
        dialog.title(f"Edit Document {doc_id}")
        dialog.geometry("600x400")
        
        # Text area for editing
        text_area = tk.Text(dialog, wrap=tk.WORD)
        text_area.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        text_area.insert("1.0", doc[0])  # Insert raw text
        
        def save_changes():
            """Save the edited document"""
            try:
                new_text = text_area.get("1.0", tk.END).strip()
                now = datetime.now().isoformat()
                
                # Update document
                self.cursor.execute('''
                    UPDATE documents 
                    SET raw_text = ?, last_modified = ?
                    WHERE id = ?
                ''', (
                    new_text,
                    now,
                    doc_id
                ))
                
                # Log edit
                self.log_action(doc_id, 'EDIT', f'Document {doc_id} edited')
                
                self.conn.commit()
                self.load_documents()  # Refresh display
                dialog.destroy()
                messagebox.showinfo("Success", "Document updated successfully")
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to update document: {str(e)}")
        
        # Add buttons
        button_frame = ttk.Frame(dialog)
        button_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(
            button_frame,
            text="Save",
            command=save_changes
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            button_frame,
            text="Cancel",
            command=dialog.destroy
        ).pack(side=tk.LEFT, padx=5)

    def view_selected_document(self):
        """View the selected document"""
        selection = self.documents_tree.selection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a document to view")
            return
        
        item = selection[0]
        doc_id = self.documents_tree.item(item)['values'][0]
        self.show_document_details(doc_id)

    def setup_search_tab(self):
        """Setup the search tab"""
        # Create search frame
        search_frame = ttk.Frame(self.search_tab)
        search_frame.pack(fill=tk.X, pady=5)
        
        # Search entry
        ttk.Label(search_frame, text="Search:").pack(side=tk.LEFT, padx=5)
        search_entry = ttk.Entry(
            search_frame,
            textvariable=self.search_var,
            width=40
        )
        search_entry.pack(side=tk.LEFT, padx=5)
        
        # Create treeview for search results
        self.search_tree = ttk.Treeview(
            self.search_tab,
            columns=("ID", "Type", "Number", "Name", "Match"),
            show="headings"
        )
        
        # Setup columns
        self.search_tree.heading("ID", text="ID")
        self.search_tree.heading("Type", text="Document Type")
        self.search_tree.heading("Number", text="Document Number")
        self.search_tree.heading("Name", text="Full Name")
        self.search_tree.heading("Match", text="Match Type")
        
        # Add scrollbar
        scrollbar = ttk.Scrollbar(
            self.search_tab,
            orient=tk.VERTICAL,
            command=self.search_tree.yview
        )
        self.search_tree.configure(yscrollcommand=scrollbar.set)
        
        # Pack elements
        self.search_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def setup_audit_tab(self):
        """Setup the audit log tab"""
        # Create treeview for audit log
        self.audit_tree = ttk.Treeview(
            self.audit_tab,
            columns=("Time", "Document ID", "Action", "User", "Details"),
            show="headings"
        )
        
        # Setup columns
        self.audit_tree.heading("Time", text="Timestamp")
        self.audit_tree.heading("Document ID", text="Document ID")
        self.audit_tree.heading("Action", text="Action")
        self.audit_tree.heading("User", text="User")
        self.audit_tree.heading("Details", text="Details")
        
        # Add scrollbar
        scrollbar = ttk.Scrollbar(
            self.audit_tab,
            orient=tk.VERTICAL,
            command=self.audit_tree.yview
        )
        self.audit_tree.configure(yscrollcommand=scrollbar.set)
        
        # Pack elements
        self.audit_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Load audit log
        self.load_audit_log()

    def handle_drop(self, event):
        """Handle drag and drop event"""
        file_path = event.data
        file_path = file_path.strip('{}').strip('"')
        self.process_image(file_path)

    def handle_enter(self, event):
        """Handle mouse enter event"""
        self.drop_label.configure(bg='lightblue')

    def handle_leave(self, event):
        """Handle mouse leave event"""
        self.drop_label.configure(bg='lightgray')

    def browse_files(self):
        """Open file browser"""
        file_types = [
            ('Image files', '*.png *.jpg *.jpeg *.bmp *.tiff'),
            ('All files', '*.*')
        ]
        file_path = filedialog.askopenfilename(filetypes=file_types)
        if file_path:
            self.process_image(file_path)

    def process_image(self, image_path):
        """Process the image and extract information"""
        try:
            # Clear previous results
            self.result_text.delete(1.0, tk.END)
            self.result_text.insert(tk.END, "Processing image...\n\n")
            self.window.update()
            
            # Extract text using DocTR
            doc = DocumentFile.from_images(image_path)
            result = self.model(doc)
            extracted_text = result.render()
            
            # Display raw text
            self.result_text.delete(1.0, tk.END)
            self.result_text.insert(tk.END, extracted_text)
            
            # Add save button
            save_btn = ttk.Button(
                self.preview_frame,
                text="Save Document",
                command=lambda: self.save_document(extracted_text)
            )
            save_btn.pack(pady=10)
            
        except Exception as e:
            error_message = f"An error occurred: {str(e)}"
            messagebox.showerror("Error", error_message)
            self.result_text.delete(1.0, tk.END)
            self.result_text.insert(tk.END, error_message)

    def parse_document_info(self, text):
        """Parse extracted text for document information"""
        info = {
            'doc_type': '',
            'doc_number': '',
            'full_name': '',
            'date_of_birth': '',
            'expiry_date': '',
            'issue_date': '',
            'metadata': {}
        }
        
        # Convert to uppercase for consistent matching
        text_upper = text.upper()
        
        # Extract document type
        doc_types = ['PASSPORT', 'DRIVER LICENSE', 'ID CARD']
        for doc_type in doc_types:
            if doc_type in text_upper:
                info['doc_type'] = doc_type
                break
        
        # Extract document number
        number_match = re.search(r'(?:ID|DL|NO|NUMBER)[.:# ]*([A-Z0-9-]{6,})', text_upper)
        if number_match:
            info['doc_number'] = number_match.group(1)
        
        # Extract name
        name_match = re.search(r'(?:NAME)[.:# ]*([A-Z ]+)', text_upper)
        if name_match:
            info['full_name'] = name_match.group(1).title()
        
        # Extract dates
        dob_match = re.search(r'(?:DOB|BIRTH)[.:# ]*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})', text_upper)
        if dob_match:
            info['date_of_birth'] = dob_match.group(1)
        
        exp_match = re.search(r'(?:EXP|EXPIRES)[.:# ]*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})', text_upper)
        if exp_match:
            info['expiry_date'] = exp_match.group(1)
        
        iss_match = re.search(r'(?:ISS|ISSUED)[.:# ]*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})', text_upper)
        if iss_match:
            info['issue_date'] = iss_match.group(1)
        
        return info

    def save_document(self, raw_text):
        """Save the document to database"""
        try:
            # Get next available ID
            self.cursor.execute("SELECT COALESCE(MAX(id), 0) FROM documents")
            next_id = self.cursor.fetchone()[0] + 1
            
            # Add timestamps
            now = datetime.now().isoformat()
            
            # Insert into database with simplified fields
            self.cursor.execute('''
                INSERT INTO documents (
                    id, raw_text, date_added, last_modified, verification_status
                ) VALUES (?, ?, ?, ?, ?)
            ''', (
                next_id,
                raw_text,
                now,
                now,
                'PENDING'
            ))
            
            doc_id = next_id
            self.conn.commit()
            
            # Log the action
            self.log_action(doc_id, 'ADD', f'Document {doc_id} added to system')
            
            # Show success message and switch to documents tab
            messagebox.showinfo("Success", f"Document saved successfully as ID: {doc_id}")
            self.notebook.select(self.documents_tab)
            
            # Refresh display
            self.load_documents()
            return True
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to add document: {str(e)}")
            return False

    def log_action(self, doc_id: int, action: str, details: str):
        """Log an action in the audit log"""
        try:
            self.cursor.execute('''
                INSERT INTO audit_log (document_id, action, timestamp, user, details)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                doc_id,
                action,
                datetime.now().isoformat(),
                "SYSTEM",
                details
            ))
            self.conn.commit()
            
            # Refresh audit log display
            self.load_audit_log()
            
        except Exception as e:
            print(f"Failed to log action: {str(e)}")

    def load_documents(self):
        """Load documents into the treeview"""
        # Clear existing items
        for item in self.documents_tree.get_children():
            self.documents_tree.delete(item)
        
        try:
            # Load documents from database with ordered IDs
            self.cursor.execute("""
                SELECT id, date_added, last_modified, verification_status 
                FROM documents 
                ORDER BY id ASC
            """)
            
            for doc in self.cursor.fetchall():
                self.documents_tree.insert(
                    "",
                    "end",
                    values=doc
                )
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load documents: {str(e)}")

    def load_audit_log(self):
        """Load audit log into the treeview"""
        # Clear existing items
        for item in self.audit_tree.get_children():
            self.audit_tree.delete(item)
        
        # Load audit log from database with simplified query
        self.cursor.execute('''
            SELECT timestamp, document_id, action, user, details
            FROM audit_log
            ORDER BY timestamp DESC
        ''')
        
        for log in self.cursor.fetchall():
            self.audit_tree.insert(
                "",
                "end",
                values=log  # Use all columns directly
            )

    def on_search_change(self, *args):
        """Handle search input changes"""
        search_term = self.search_var.get().strip()
        
        # Clear existing search results
        for item in self.search_tree.get_children():
            self.search_tree.delete(item)
        
        if not search_term:
            return
        
        # Perform search
        self.cursor.execute('''
            SELECT id, doc_type, doc_number, full_name
            FROM documents
            WHERE doc_number LIKE ? OR full_name LIKE ?
            ORDER BY date_added DESC
        ''', (f'%{search_term}%', f'%{search_term}%'))
        
        for result in self.cursor.fetchall():
            match_type = "Number" if search_term in result[2] else "Name"
            self.search_tree.insert(
                "",
                "end",
                values=(result[0], result[1], result[2], result[3], match_type)
            )

    def on_document_double_click(self, event):
        """Handle double-click on document in treeview"""
        item = self.documents_tree.selection()[0]
        doc_id = self.documents_tree.item(item)['values'][0]
        self.show_document_details(doc_id)

    def show_document_details(self, doc_id: int):
        """Show dialog with document details"""
        # Get document data
        self.cursor.execute(
            "SELECT id, raw_text, date_added, last_modified, verification_status FROM documents WHERE id = ?",
            (doc_id,)
        )
        doc = self.cursor.fetchone()
        
        if not doc:
            return
        
        # Create dialog
        dialog = tk.Toplevel(self.window)
        dialog.title(f"Document Details - ID: {doc[0]}")
        dialog.geometry("500x600")
        
        # Create notebook for tabs
        notebook = ttk.Notebook(dialog)
        notebook.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Details tab
        details_tab = ttk.Frame(notebook)
        notebook.add(details_tab, text="Details")
        
        details = [
            ("Document ID:", doc[0]),
            ("Date Added:", doc[2]),
            ("Last Modified:", doc[3]),
            ("Verification Status:", doc[4])
        ]
        
        for i, (label, value) in enumerate(details):
            ttk.Label(details_tab, text=label).grid(row=i, column=0, pady=5, padx=5, sticky="e")
            ttk.Label(details_tab, text=value).grid(row=i, column=1, pady=5, padx=5, sticky="w")
        
        # Raw text tab
        raw_tab = ttk.Frame(notebook)
        notebook.add(raw_tab, text="Raw Text")
        
        raw_text = tk.Text(raw_tab, wrap=tk.WORD, height=20)
        raw_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        raw_text.insert("1.0", doc[1] or "No raw text available")
        raw_text.configure(state="disabled")
        
        # Add close button
        ttk.Button(
            dialog,
            text="Close",
            command=dialog.destroy
        ).pack(pady=10)

    def run(self):
        """Run the application"""
        self.window.mainloop()

    def __del__(self):
        """Cleanup on exit"""
        if hasattr(self, 'conn'):
            self.conn.close()

def main():
    app = DocumentManager()
    app.run()

if __name__ == "__main__":
    main() 