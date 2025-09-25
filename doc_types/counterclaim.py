""" Counterclaim aka "Intampinare"""

COUNTERCLAIM_ANNOTATION_SYSTEM_PROMPT = """Ești un asistent inteligent specializat în analiza documentelor juridice. Poți extrage și identifica diferite tipuri de entități și informații din documentele juridice românești. Vei răspunde doar cu entitățile extrase, fără a altera textul original. Textul de intrare va avea paragrafele separate prin tagurile <p> și </p>. Entitățile extrase vor conține aceste taguri."""

COUNTERCLAIM_SUMMARY_SYSTEM_PROMPT = """Ești un asistent inteligent specializat în rezumarea și corectarea documentelor juridice românești."""

COUNTERCLAIM_ANNOTATION_MODEL_CONFIG = {
    'isTemei': "counterclaim-istemei",
    'isProba': "counterclaim-isproba",
    'isSelected': "counterclaim-isselect",
    'isCerere': "counterclaim-iscerere",
    'isReclamant': "counterclaim-isreclamant",
    'isParat': "counterclaim-isparat"
}

COUNTERCLAIM_SUMMARY_MODEL_CONFIG = {
    'isTemei': "meta-llama/Llama-3.1-8B-Instruct",
    'isProba': "meta-llama/Llama-3.1-8B-Instruct",
    'isSelected': "meta-llama/Llama-3.1-8B-Instruct",
    'isCerere': "rewrite-cerere",
    'isReclamant': "meta-llama/Llama-3.1-8B-Instruct",
    'isParat': "meta-llama/Llama-3.1-8B-Instruct"
}

COUNTERCLAIM_ANNOTATE_PROMPTS = {
    'isTemei': """Extrage temeiul legal din documentul de mai sus. Temeiul legal reprezintă fundamentul juridic al unei cereri sau acțiuni - articolele de lege, ordonanțele, codurile și actele normative pe care se bazează argumentația. De obicei este introdus prin formulări precum "În drept", "invocăm", "ne întemeiem", "drept, în art.", "Îmi întemeiez cererea pe" sau "Pe temeiul". Exemple de temeuri legale: "În drept, art.31 din OG2/2001", "drept, în art. 31 şi 32 din O.G. nr. 2/2001 (actualizată)", "În drept. îmi întemeiez cererea pe dispozițiile art. 31-36 din O.G. nr. 2/2001 privind regimul juridic al contravențiilor, art. 6 din Convenția Europeană a Drepturilor Omului și art. 118 din O.U.G. Nr 195/2002 privind circulația pe drumurile publice". Identifică și extrage toate referințele la acte normative, inclusiv numărul articolului, denumirea și numărul actului normativ.""",
    
    'isProba': """Extrage dovezile și probele menționate în documentul de mai jos. Acestea pot include documente, contracte, facturi, martori, expertize, înscrisuri sau alte mijloace de probă care susțin cauza. Deseori sunt introduse prin formulări precum "în probațiune" sau "dovedire", "interogatoriu", "în conformitate cu ... anexăm", "înscrisuri".""",
    
    'isSelected': """Extrage descrierea faptelor și cicumstanțelor din documentul de mai sus. De obicei, aceste informații sunt introduse prin "În fapt", "Astfel", "La data de" și descriu versiunea părții pârâte despre evenimentele care au dus la conflictul juridic.""",
    
    'isCerere': """Extrage cererea propriu-zisă din documentul de mai sus - ce anume se solicită de la instanță (respingerea unei acțiuni sau plângeri, anularea unui act, admitere, executarea unei obligații, etc.). In general, cererea este introdusă prin formulări precum "în temeiul celor de mai sus, solicit", "solicit", "în consecință, solicit", "solicit să se dispună", "solicit să se oblige", "solicit să se constate", etc.""",
    
    'isReclamant': """Extrage informațiile despre reclamant din documentul de mai sus (partea care a scris această întâmpinare, fie o persoană, fie o entitate precum o instituție sau o persoană juridică). De obicei este introdus prin "petent", "in contradictoriu cu", "contestatorul", "numitul", "reclamantul". Ne interesează doar numele complet.""",
    
    'isParat': """Extrage numele despre entitatea care se apara in documentul de mai sus (partea care se apără în această întâmpinare, care a scris documentul; pot fi mai multe părți, fie persoane fizice, fie entități precum instituții sau persoane juridice). De obicei, este introdus prin „subsemnatul" și se află în prima parte a documentului. Ne interesează doar numele complet si nemodificat."""
}

COUNTERCLAIM_SUMMARY_PROMPTS = {
    'isTemei': """Corecteaza textul temeiului legal dacă este cazul, acesta ar trebui să fie la persoana a III-a, forma pasivă, timpul perfect compus și este introdus prin "În drept".
De exemplu, "În drept, au fost invocate următoarele prevederi...". Vei răspunde doar cu textul corectat, fără alte explicații.""",
    
    'isProba': """Corectează textul probei dacă este cazul, acesta ar trebui să fie la persoana a III-a, forma pasivă, timpul perfect compus și este introdus prin "În probațiune,".
Vei răspunde doar cu textul corectat, fără alte explicații.""",

    'isSelected': """Rezumă descrierea faptelor și circumstanțelor descrise de pârât în textul extras de mai sus, care să cuprindă toate argumentele esențiale.
Rezumatul va trebui scris la persoana a III-a, forma activă, modul indicativ și timpul perfect compus.
Textul va fi structurat in paragrafe, fiecare corespunzând unei idei principale. 
Pentru a reflecta clar poziția procesuală a părții, fiecare paragraf argumentativ (idee principală) va utiliza expresii de tipul: „A arătat că”, „A susținut că”, „A învederat că”, „A menționat că”, „A expus faptul că”, „A relatat că”.
Textul va fi introdus prin „În motivare,”.
Vei răspunde doar cu textul rezumat, fără alte explicații.""",

    'isCerere': """Corecteaza textul cererii de mai sus dacă este cazul, acesta ar trebui să fie la persoana a III-a, forma activa, timpul trecut, perfect compus cu diacritice. Vor fi folosite pronume demonstrative, persoana a III-a, (e.g., acestora, acestuia). De exemplu, noastră se va transforma in acestora.
Cine a scris cererea: "{isReclamant}". 
Textul corectat va incepe mereu cu „a solicitat" sau „au solicitat". Pentru un reclamant (e.g. un singur nume de persoana, companie, institutie), va incepe cu "a solicitat", pentru mai multi reclamanti cu "au solicitat".
Vei răspunde doar cu textul corectat, fără alte explicații.""",

    'isReclamant': """Textul de mai sus conține unul sau mai multe nume de persoane/instituții. Va trebui să le formatezi pentru a avea o listă clară, separată prin virgulă. Vei răspunde doar cu lista, fără alte explicații.""",

    'isParat': """Textul de mai sus conține mai multe nume de persoane/instituții. Vreau să le formatăm pentru a avea o listă clară, separată prin virgulă. Vei răspunde doar cu lista, fără alte explicații.""",

}

def get_counterclaim_annotation_prompts() -> dict:
    """Get annotation prompts for counterclaim document type"""
    return COUNTERCLAIM_ANNOTATE_PROMPTS

def get_counterclaim_summary_prompts() -> dict:
    """Get summary prompts for counterclaim document type"""
    return COUNTERCLAIM_SUMMARY_PROMPTS

def get_counterclaim_annotation_system_prompt() -> str:
    """Get annotation system prompt for counterclaim document type"""
    return COUNTERCLAIM_ANNOTATION_SYSTEM_PROMPT

def get_counterclaim_summary_system_prompt() -> str:
    """Get summary system prompt for counterclaim document type"""
    return COUNTERCLAIM_SUMMARY_SYSTEM_PROMPT

def get_counterclaim_annotation_model_config() -> dict:
    """Get annotation model configuration for counterclaim document type"""
    return COUNTERCLAIM_ANNOTATION_MODEL_CONFIG

def get_counterclaim_summary_model_config() -> dict:
    """Get summary model configuration for counterclaim document type"""
    return COUNTERCLAIM_SUMMARY_MODEL_CONFIG
