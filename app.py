"""
FastAPI wrapper for Word to XML conversion algorithm
Deploy this file to a Python server (Railway, Render, Google Cloud Run, etc.)
"""

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import os
import io
import re
import pandas as pd
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from lxml import etree
from typing import Dict, List, Tuple
from sklearn.feature_extraction import DictVectorizer
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline

app = FastAPI(
    title="Word to XML Conversion API",
    description="ML-based Word to XML converter using DTD schema",
    version="1.0.0"
)

# Enable CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- DTD Configuration ---
NS_CL = "http://xml.cengage-learning.com/cendoc-core"
NS_MAP = {'cl': NS_CL}

def cl(tag):
    """Helper function to create a namespaced tag for the output XML."""
    return f"{{{NS_CL}}}{tag}"

# --- 1. ML FEATURE EXTRACTION ---

def extract_features_from_docx(docx_file_stream: io.BytesIO) -> List[Dict]:
    """
    Extracts a list of paragraphs, each represented as a dictionary of features
    (text, font_size, bold, etc.) for the ML model.
    """
    document = Document(docx_file_stream)
    features_list = []

    # List of junk patterns to ignore
    junk_patterns = [
        '[[Insert',
        'istock.com',
        '©nampix/Shutterstock.com',
        'Panther Media GmbH/Alamy Stock Photo',
        'Mediscan / Alamy',
        'SPL/Science Source',
        'Martin Rotker/Phototake',
        'Dr. P. Marazzi/Science Photo Library/Science Source',
        'Courtesy of Dr. David King. © Myrna Engler',
        'Mediscan / Alamy',
        'SPL/Science Source',
        'Martin Rotker/Phototake'
    ]

    # State variable to track if we are inside a marginal term block
    skipping_marginal_term = False

    for para in document.paragraphs:
        text = para.text.strip()

        # Check for the end marker first
        if text == "[[End Marginal Term here]]":
            skipping_marginal_term = False
            continue

        # Check for the start marker
        if text == "[[Start Marginal Term here]]":
            skipping_marginal_term = True
            continue

        # If we are in "skip mode", ignore the paragraph
        if skipping_marginal_term:
            continue

        # Skip junk lines and empty lines
        if not text or any(jp in text for jp in junk_patterns):
            continue

        # Extract features from the first run
        font_size = 12.0
        is_bold = False
        is_italic = False
        if para.runs:
            run = para.runs[0]
            if run.font.size:
                font_size = run.font.size.pt
            if run.font.bold is not None:
                is_bold = run.font.bold
            if run.font.italic is not None:
                is_italic = run.font.italic

        # Get alignment
        alignment = para.paragraph_format.alignment
        align_str = 'center' if alignment == WD_ALIGN_PARAGRAPH.CENTER else 'left'

        # Check for list numbering
        is_list = 'List' in (para.style.name or '')

        # Feature Dictionary
        features_list.append({
            'text': text,
            'font_size': font_size,
            'is_bold': is_bold,
            'is_italic': is_italic,
            'alignment': align_str,
            'is_list': is_list,
            'text_length': len(text),
            'starts_with_num': text.startswith(tuple(str(i) for i in range(10))),
            'starts_with_lo': text.startswith("LO "),
            'starts_with_table': text.startswith("TABLE "),
            'starts_with_figure': text.startswith("> FIGURE") or text.startswith("> PHOTO")
        })

    return features_list

# --- 2. ML MODEL & TRAINING ---

def create_and_train_model() -> Pipeline:
    """Creates and trains the ML pipeline."""
    sample_data = [
        ({'font_size': 18.0, 'is_bold': True, 'starts_with_num': True, 'is_list': False, 'starts_with_lo': False, 'starts_with_table': False, 'starts_with_figure': False, 'alignment': 'left', 'is_italic': False, 'text_length': 30}, 'cl:title'),
        ({'font_size': 14.0, 'is_bold': True, 'text_length': 37, 'is_list': False, 'starts_with_lo': False, 'starts_with_table': False, 'starts_with_figure': False, 'alignment': 'left', 'is_italic': False, 'starts_with_num': False}, 'cl:heading_outline'),
        ({'font_size': 14.0, 'is_bold': True, 'starts_with_num': True, 'is_list': False, 'starts_with_lo': False, 'starts_with_table': False, 'starts_with_figure': False, 'alignment': 'left', 'is_italic': False, 'text_length': 30}, 'cl:sect1/cl:title'),
        ({'font_size': 12.0, 'is_bold': True, 'starts_with_lo': True, 'is_list': False, 'starts_with_table': False, 'starts_with_figure': False, 'alignment': 'left', 'is_italic': False, 'text_length': 100}, 'cl:learn-obj'),
        ({'font_size': 12.0, 'is_bold': False, 'text_length': 80, 'is_list': False, 'starts_with_lo': False, 'starts_with_table': False, 'starts_with_figure': False, 'alignment': 'left', 'is_italic': False, 'starts_with_num': False}, 'cl:para'),
        ({'font_size': 12.0, 'is_bold': False, 'text_length': 150, 'is_list': False, 'starts_with_lo': False, 'starts_with_table': False, 'starts_with_figure': False, 'alignment': 'left', 'is_italic': False, 'starts_with_num': False}, 'cl:para'),
        ({'font_size': 12.0, 'is_bold': False, 'starts_with_table': True, 'is_list': False, 'starts_with_lo': False, 'starts_with_figure': False, 'alignment': 'left', 'is_italic': False, 'text_length': 30}, 'cl:table'),
        ({'font_size': 12.0, 'is_bold': False, 'starts_with_figure': True, 'is_list': False, 'starts_with_lo': False, 'starts_with_table': False, 'alignment': 'left', 'is_italic': False, 'text_length': 30}, 'cl:figure'),
    ]

    train_df = pd.DataFrame(sample_data, columns=['features', 'tag'])

    feature_dicts = [d.copy() for d in train_df['features']]
    for d in feature_dicts:
        d.pop('text', None)

    model_pipeline = Pipeline([
        ('vectorizer', DictVectorizer(sparse=False)),
        ('classifier', RandomForestClassifier(n_estimators=50, random_state=42))
    ])

    model_pipeline.fit(feature_dicts, train_df['tag'])

    return model_pipeline

# --- 3. XML ASSEMBLY ---

class ChapterXMLConverter:
    """Converts structured data predictions into DTD-compliant XML."""
    def __init__(self, predictions: List[Tuple[Dict, str]]):
        self.data = [item for item in predictions if isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], dict)]
        self.root = None
        self.id_counter = 0

    def _get_id(self):
        """Generates a unique identifier."""
        self.id_counter += 1
        return f'AUTO_ID_{self.id_counter}'

    def _apply_inline_formatting(self, parent_element, text: str):
        """Applies key term replacement and footnote tags."""
        SUPER_TO_REGULAR = {
            '¹': '1', '²': '2', '³': '3', '⁰': '0', '⁴': '4',
            '⁵': '5', '⁶': '6', '⁷': '7', '⁸': '8', '⁹': '9'
        }

        key_terms = {
            'hepatic portal vein': 'AUTO_KT_1', 'cirrhosis': 'AUTO_KT_2',
            'hyponatremia': 'AUTO_KT_3', 'insulin resistance': 'AUTO_KT_4',
            'steatohepatitis': 'AUTO_KT_5', 'hepatomegaly': 'AUTO_KT_6',
            'hepatitis': 'AUTO_KT_7', 'jaundice': 'AUTO_KT_8',
            'pruritus': 'AUTO_KT_9', 'portal hypertension': 'AUTO_KT_10',
        }
        style_terms = {
            'fatigue': 'AUTO_BOLD_1',
        }

        kt_regex = r'|'.join(r'\b' + re.escape(k) + r'\b' for k in key_terms.keys())
        style_regex = r'|'.join(r'\b' + re.escape(k) + r'\b' for k in style_terms.keys())
        footnote_regex = r'([¹²³⁰⁴⁵⁶⁷⁸⁹]+)'

        combined_regex = f'({kt_regex}|{style_regex}|{footnote_regex})'
        parts = re.split(combined_regex, text, flags=re.IGNORECASE)

        last_node = None

        for part in parts:
            if not part:
                continue

            part_lower = part.lower()

            if re.fullmatch(footnote_regex, part):
                regular_num = "".join(SUPER_TO_REGULAR.get(char, '') for char in part)
                if not regular_num: regular_num = "X"

                fn_node = etree.Element(cl('footnote'),
                                        identifier=self._get_id(),
                                        type="numfootnote",
                                        fnposition=regular_num,
                                        **{'footnote-override': 'footnote'})

                para_node = etree.SubElement(fn_node, cl('para'), identifier=self._get_id())
                para_node.text = f'[Insert reference {regular_num} text here]'

                parent_element.append(fn_node)
                last_node = fn_node

            elif part_lower in key_terms:
                kt_node = etree.Element(cl('key-term-entry'), identifier=self._get_id())
                term_node = etree.SubElement(kt_node, cl('key-term'), identifier=self._get_id())
                term_node.text = part

                parent_element.append(kt_node)
                last_node = kt_node

            elif part_lower in style_terms:
                style_node = etree.Element(cl('style'), identifier=self._get_id(), styles="bold")
                style_node.text = part

                parent_element.append(style_node)
                last_node = style_node

            else:
                if last_node is not None:
                    last_node.tail = (last_node.tail or '') + part
                else:
                    parent_element.text = (parent_element.text or '') + part

    def _build_chapter_meta(self, chapter_tag):
        meta_data_tuple = next((item for item in self.data if item[1] == 'cl:title'), None)
        if not meta_data_tuple: return

        meta_data = meta_data_tuple[0]

        complex_meta = etree.SubElement(chapter_tag, cl('complex-meta'), identifier=self._get_id())
        title = etree.SubElement(complex_meta, cl('title'), identifier=self._get_id())
        title.text = meta_data['text']
        label = etree.SubElement(complex_meta, cl('label'), identifier=self._get_id())
        ordinal = etree.SubElement(label, cl('ordinal'))
        ordinal.text = meta_data['text'].split(" ")[0]

    def _build_chapter_opener(self, chapter_tag) -> int:
        """Builds the chapter opener."""
        opener = etree.SubElement(chapter_tag, cl('opener'), identifier=self._get_id())

        intro = etree.SubElement(opener, cl('introduction'), identifier=self._get_id(), type='covgt')
        complex_meta = etree.SubElement(intro, cl('complex-meta'), identifier=self._get_id())
        etree.SubElement(complex_meta, cl('title'), identifier=self._get_id()).text = "Nutrition in the Clinical Setting"

        first_section_index = -1
        for i, (features, tag) in enumerate(self.data):
            if tag == 'cl:sect1/cl:title':
                first_section_index = i
                break

        slice_index = first_section_index if first_section_index != -1 else len(self.data)
        intro_predictions = self.data[:slice_index]

        for features, tag in intro_predictions:
            if tag == 'cl:para':
                para = etree.SubElement(intro, cl('para'), identifier=self._get_id())
                self._apply_inline_formatting(para, features['text'])

        return first_section_index

    def _build_main_sections(self, chapter_tag, start_index: int):
        """Builds the main sections."""
        current_sect_tag = None

        if start_index == -1:
            return

        main_content_predictions = self.data[start_index:]

        for features, tag in main_content_predictions:
            if tag == 'cl:sect1/cl:title':
                current_sect_tag = etree.SubElement(chapter_tag, cl('sect1'), identifier=self._get_id())

                complex_meta = etree.SubElement(current_sect_tag, cl('complex-meta'), identifier=self._get_id())
                title = etree.SubElement(complex_meta, cl('title'), identifier=self._get_id())
                title.text = features['text']
                label = etree.SubElement(complex_meta, cl('label'), identifier=self._get_id())
                ordinal = etree.SubElement(label, cl('ordinal'))
                ordinal.text = features['text'].split(" ")[0]

            elif tag == 'cl:para' and current_sect_tag is not None:
                para = etree.SubElement(current_sect_tag, cl('para'), identifier=self._get_id())
                self._apply_inline_formatting(para, features['text'])

            elif tag == 'cl:table' and current_sect_tag is not None:
                table_wrap = etree.SubElement(current_sect_tag, cl('table-wrapper'), identifier=self._get_id())
                etree.SubElement(table_wrap, cl('title'), identifier=self._get_id()).text = features['text']

            elif tag == 'cl:figure' and current_sect_tag is not None:
                figure_wrap = etree.SubElement(current_sect_tag, cl('figure'), identifier=self._get_id())
                etree.SubElement(figure_wrap, cl('title'), identifier=self._get_id()).text = features['text']

            elif tag == 'cl:learn-obj' and current_sect_tag is not None:
                lo = etree.SubElement(current_sect_tag, cl('learn-obj'), identifier=self._get_id())
                lo.text = features['text']

    def convert(self) -> str:
        """Main conversion flow."""
        NSMAP_ROOT = {
            'cl': NS_CL,
            'm': "http://www.w3.org/1998/Math/MathML",
            'xsi': "http://www.w3.org/2001/XMLSchema-instance",
            'cl-ext': "http://xml.cengage-learning.com/cendoc-ext",
        }

        self.root = etree.Element(
            cl('doc'),
            identifier='CH25_LIVER_GALLSTONES',
            nsmap=NSMAP_ROOT
        )

        self.root.set('{http://www.w3.org/2001/XMLSchema-instance}schemaLocation',
                        f'{NS_CL} cendoc.xsd')

        doc_meta = etree.SubElement(self.root, cl('doc-meta'), identifier=self._get_id())
        etree.SubElement(doc_meta, cl('title'), identifier=self._get_id()).text = "Understanding Normal & Clinical Nutrition - Kim"
        etree.SubElement(doc_meta, cl('isbn'), attrib={'length': '13'}).text = "9780357974025"
        etree.SubElement(self.root, cl('front-matter'), identifier=self._get_id())

        body_matter = etree.SubElement(self.root, cl('body-matter'), identifier=self._get_id())
        chapter = etree.SubElement(body_matter, cl('chapter'), identifier=self._get_id())

        self._build_chapter_meta(chapter)
        main_content_start_index = self._build_chapter_opener(chapter)
        self._build_main_sections(chapter, main_content_start_index)

        xml_output_bytes = etree.tostring(self.root,
                                        pretty_print=True,
                                        encoding='utf-8',
                                        xml_declaration=False)

        xml_string = xml_output_bytes.decode('utf-8')
        final_xml = '<?xml version="1.0" encoding="utf-8"?>\n' + xml_string
        return final_xml

# --- 4. WORKFLOW AUTOMATION ---

def run_ml_conversion_workflow(docx_content: bytes) -> str:
    """Trains ML model and converts document."""
    model = create_and_train_model()

    docx_stream = io.BytesIO(docx_content)
    new_doc_features = extract_features_from_docx(docx_stream)

    predict_feature_dicts = [d.copy() for d in new_doc_features]
    for d in predict_feature_dicts:
        d.pop('text', None)

    predicted_tags = model.predict(predict_feature_dicts)

    predictions_with_features = list(zip(new_doc_features, predicted_tags))

    converter = ChapterXMLConverter(predictions_with_features)
    xml_output = converter.convert()
    return xml_output

# --- FASTAPI ENDPOINTS ---

@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "message": "Word to XML Conversion API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "message": "API is running"}

@app.post("/convert")
async def convert_document(
    word_file: UploadFile = File(...),
    dtd_file: UploadFile = File(None)
):
    """
    Main conversion endpoint.
    
    Parameters:
    - word_file: Word document to convert (.doc or .docx) - Required
    - dtd_file: DTD XML file (for context, optional)
    
    Returns:
    - JSON with success status and XML content
    """
    try:
        # Validate word file
        if not word_file:
            raise HTTPException(status_code=400, detail="No word_file provided")
        
        if not word_file.filename:
            raise HTTPException(status_code=400, detail="Empty filename")
        
        # Validate file extension
        if not word_file.filename.endswith(('.doc', '.docx')):
            raise HTTPException(
                status_code=400, 
                detail="Invalid file type. Only .doc and .docx files are supported"
            )

        # Read the Word file content
        word_content = await word_file.read()

        # Run the conversion
        xml_output = run_ml_conversion_workflow(word_content)

        # Return the XML output
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "xml_content": xml_output,
                "word_filename": word_file.filename
            }
        )

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__
            }
        )

# For local testing with uvicorn
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
