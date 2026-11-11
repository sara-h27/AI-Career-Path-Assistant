"""Small deterministic normalization with optional Hazm; original text stays in session only."""
import re

class PersianTextPreprocessor:
    CHAR_MAP = str.maketrans({'ي':'ی','ى':'ی','ك':'ک','ؤ':'و','إ':'ا','أ':'ا','ٱ':'ا','ة':'ه','ـ':'','\u200e':'','\u200f':'','\ufeff':''})
    DIGIT_MAP = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩','01234567890123456789')
    TECH_SYNONYMS = {'پایتون':'python','پایتن':'python','اس کیو ال':'sql','اس‌کیو‌ال':'sql','سیکوئل':'sql','اکسل':'excel','داکر':'docker','گیت':'git','لینوکس':'linux','جاوا اسکریپت':'javascript','جاوااسکریپت':'javascript','تایپ اسکریپت':'typescript','تایپ‌اسکریپت':'typescript','ری اکت':'react','ری‌اکت':'react','پانداس':'pandas','نامپای':'numpy','پاور بی آی':'power_bi','تبلو':'tableau'}

    def __init__(self, use_hazm=False, normalize_tech_terms=True):
        self.hazm_normalizer = None
        self.normalize_tech_terms = normalize_tech_terms
        if use_hazm:
            try:
                from hazm import Normalizer
                self.hazm_normalizer = Normalizer()
            except Exception:
                pass

    def preprocess(self, text):
        if not isinstance(text, str):
            return ''
        text = re.sub('[\u064b-\u065f\u0670]', '', text.translate(self.CHAR_MAP))
        text = text.translate(self.DIGIT_MAP)
        if self.hazm_normalizer:
            try:
                text = self.hazm_normalizer.normalize(text)
            except Exception:
                text = self._spacing(text)
        else:
            text = self._spacing(text)
        text = text.translate(self.DIGIT_MAP)
        text = re.sub(r'[\u200c]+', '\u200c', text)
        text = re.sub(r'\s+', ' ', text).strip()
        if self.normalize_tech_terms:
            for fa, en in sorted(self.TECH_SYNONYMS.items(), key=lambda x:-len(x[0])):
                text = re.sub(r'(?<!\w)'+re.escape(fa)+r'(?!\w)', en, text, flags=re.I)
        return text

    @staticmethod
    def _spacing(text):
        text = re.sub(r'\b(ن?می)\s+(?=[\u0600-\u06ff])', r'\1‌', text)
        return re.sub(r'(?<=[\u0600-\u06ff])\s+(ها|های|هایی|هایم|هایت|هایش)\b', r'‌\1', text)
