import cv2
import pytesseract
import numpy as np
from PIL import Image
import tkinter as tk
from tkinter import filedialog, messagebox
import os
from tkinterdnd2 import DND_FILES, TkinterDnD

class OCRApp:
    def __init__(self):
        self.window = TkinterDnD.Tk()
        self.window.title("Document OCR")
        self.window.geometry("600x400")
        
        # Create main frame
        self.main_frame = tk.Frame(self.window, padx=20, pady=20)
        self.main_frame.pack(expand=True, fill='both')
        
        # Create drag & drop label
        self.drop_label = tk.Label(
            self.main_frame,
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
        self.browse_btn = tk.Button(
            self.main_frame,
            text="Browse Files",
            command=self.browse_files
        )
        self.browse_btn.pack(pady=10)
        
        # Result text area
        self.result_text = tk.Text(self.main_frame, height=10, width=50)
        self.result_text.pack(pady=10)

    def handle_drop(self, event):
        file_path = event.data
        # Remove curly braces and extra quotes if present
        file_path = file_path.strip('{}').strip('"')
        self.process_image(file_path)

    def handle_enter(self, event):
        self.drop_label.configure(bg='lightblue')

    def handle_leave(self, event):
        self.drop_label.configure(bg='lightgray')

    def browse_files(self):
        file_types = [
            ('Image files', '*.png *.jpg *.jpeg *.bmp *.tiff'),
            ('All files', '*.*')
        ]
        file_path = filedialog.askopenfilename(filetypes=file_types)
        if file_path:
            self.process_image(file_path)

    def process_image(self, image_path):
        try:
            # Clear previous results
            self.result_text.delete(1.0, tk.END)
            self.result_text.insert(tk.END, "Processing image...\n")
            self.window.update()
            
            # Extract text
            extracted_text = self.extract_text(image_path)
            
            # Display results
            self.result_text.delete(1.0, tk.END)
            if extracted_text.strip():
                self.result_text.insert(tk.END, f"Extracted Text:\n{extracted_text}")
            else:
                self.result_text.insert(tk.END, "No text was detected in the image.")
                
        except Exception as e:
            error_message = f"An error occurred: {str(e)}"
            print(error_message)  # Print to console for debugging
            messagebox.showerror("Error", error_message)
            self.result_text.delete(1.0, tk.END)
            self.result_text.insert(tk.END, error_message)

    def preprocess_image(self, image_path):
        try:
            # Read the image using OpenCV
            image = cv2.imread(image_path)
            if image is None:
                raise Exception("Failed to load image")
            
            # Resize image if too large (helps with processing)
            max_dimension = 1800
            height, width = image.shape[:2]
            if max(height, width) > max_dimension:
                scale = max_dimension / max(height, width)
                image = cv2.resize(image, None, fx=scale, fy=scale)
            
            # Convert to grayscale
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            
            # Apply bilateral filter to remove noise while preserving edges
            denoised = cv2.bilateralFilter(gray, 9, 75, 75)
            
            # Increase contrast using CLAHE
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
            contrast_enhanced = clahe.apply(denoised)
            
            # Apply adaptive thresholding with refined parameters
            binary = cv2.adaptiveThreshold(
                contrast_enhanced,
                255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY,
                21,  # Slightly larger block size for better text detection
                10   # Adjusted constant for better contrast
            )
            
            return binary
            
        except Exception as e:
            print(f"Error in preprocessing: {str(e)}")
            raise

    def extract_text(self, image_path):
        try:
            # Clear previous results
            self.result_text.delete(1.0, tk.END)
            self.result_text.insert(tk.END, "Processing image...\n")
            self.window.update()
            
            # Preprocess the image
            processed_image = self.preprocess_image(image_path)
            
            # Configure tesseract parameters
            custom_config = r'--oem 3 --psm 6 -l eng --dpi 300'
            
            # Extract text using pytesseract
            text = pytesseract.image_to_string(
                processed_image,
                config=custom_config,
                lang='eng'
            )
            
            # Clean up the extracted text
            cleaned_text = self.post_process_text(text)
            
            # Display results
            self.result_text.delete(1.0, tk.END)
            if cleaned_text.strip():
                self.result_text.insert(tk.END, f"Extracted Text:\n{cleaned_text}")
            else:
                self.result_text.insert(tk.END, "No text was detected in the image.")
            
            return cleaned_text
            
        except Exception as e:
            error_message = f"An error occurred: {str(e)}"
            print(error_message)  # Print to console for debugging
            messagebox.showerror("Error", error_message)
            self.result_text.delete(1.0, tk.END)
            self.result_text.insert(tk.END, error_message)

    def post_process_text(self, text):
        try:
            # Split into lines
            lines = text.split('\n')
            
            # Process each line
            cleaned_lines = []
            for line in lines:
                # Basic cleaning
                line = line.strip()
                if not line:
                    continue
                
                # Remove extra spaces
                line = ' '.join(line.split())
                
                # Fix common OCR mistakes
                line = self.fix_common_errors(line)
                
                # Add line if it's valid
                if len(line) > 2 and any(c.isalnum() for c in line):
                    cleaned_lines.append(line)
            
            # Join lines back together
            cleaned_text = '\n'.join(cleaned_lines)
            
            return cleaned_text
            
        except Exception as e:
            print(f"Error in post-processing: {str(e)}")
            return text

    def fix_common_errors(self, text):
        """Fix common OCR errors and typos."""
        # Only fix the most common and reliable corrections
        common_fixes = {
            '|': 'I',
            '[': 'I',
            ']': 'I',
            '{': '(',
            '}': ')',
        }
        
        for wrong, correct in common_fixes.items():
            text = text.replace(wrong, correct)
        
        return text

    def run(self):
        self.window.mainloop()

def main():
    # Set Tesseract path - update this path to match your installation directory
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
    
    os.environ['PATH'] = r'C:\Program Files\Tesseract-OCR' + os.environ['PATH']
    
    app = OCRApp()
    app.run()

if __name__ == "__main__":
    main()
