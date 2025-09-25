""" Subpoena aka "Cerere de chemare în judecată"""

SUBPOENA_ANNOTATION_SYSTEM_PROMPT = """Ești un asistent inteligent specializat în analiza documentelor juridice. Poți extrage și identifica diferite tipuri de entități și informații din documentele juridice românești. Vei răspunde doar cu entitățile extrase, fără a altera textul original. Textul de intrare va avea paragrafele separate prin tagurile <p> și </p>. Entitățile extrase vor conține aceste taguri."""

SUBPOENA_SUMMARY_SYSTEM_PROMPT = """Ești un asistent inteligent specializat în analiza, sumarizarea si corectarea documentelor juridice românești."""

SUBPOENA_ANNOTATION_MODEL_CONFIG = {
    'isTemei': "subpoema-istemei",
    'isProba': "subpoema-isproba",
    'isSelected': "subpoema-isselect",
    'isCerere': "subpoema-iscerere",
    'isReclamant': "subpoema-isreclamant",
    'isParat': "subpoema-isparat"
}

SUBPOENA_SUMMARY_MODEL_CONFIG = {
    'isTemei': "meta-llama/Llama-3.1-8B-Instruct",
    'isProba': "meta-llama/Llama-3.1-8B-Instruct",
    'isSelected': "summary-select",
    'isCerere': "rewrite-cerere",
    'isReclamant': "meta-llama/Llama-3.1-8B-Instruct",
    'isParat': "meta-llama/Llama-3.1-8B-Instruct"
}

SUBPOENA_ANNOTATE_PROMPTS = {
    'isTemei': """Extrage temeiul legal din documentul de mai jos. Temeiul legal reprezintă fundamentul juridic al unei cereri sau acțiuni - articolele de lege, ordonanțele, codurile și actele normative pe care se bazează argumentația. De obicei este introdus prin formulări precum "În drept", "drept, în art.", "Îmi întemeiez cererea pe" sau "Pe temeiul". Exemple de temeuri legale: "În drept, art.31 din OG2/2001", "drept, în art. 31 şi 32 din O.G. nr. 2/2001 (actualizată)", "În drept. îmi întemeiez cererea pe dispozițiile art. 31-36 din O.G. nr. 2/2001 privind regimul juridic al contravențiilor, art. 6 din Convenția Europeană a Drepturilor Omului și art. 118 din O.U.G. Nr 195/2002 privind circulația pe drumurile publice". Identifică și extrage toate referințele la acte normative, inclusiv numărul articolului, denumirea și numărul actului normativ.""",
    
    'isProba': """Extrage dovezile și probele menționate în documentul de mai jos. Acestea pot include documente, contracte, facturi, martori, expertize, înscrisuri sau alte mijloace de probă care susțin cauza. Deseori sunt introduse prin formulări precum "în probațiune" sau "dovedire", "interogatoriu", "în conformitate cu ... anexăm", "înscrisuri".""",
    
    'isSelected': """Extrage descrierea faptelor și circumstanțelor cazului din documentul de mai jos. De obicei, aceste informații sunt introduse prin "În fapt" și descriu situația care a dus la conflictul juridic. Acesta este evenimentul relatat de catre reclamant""",
    
    'isCerere': """Extrage cererea propriu-zisă din documentul de mai jos - ce anume solicită reclamantul de la instanță (despăgubiri, anularea unui act, executarea unei obligații, etc.). In general, cererea este introdusă prin formulări precum "în temeiul celor de mai sus, solicit", "solicit", "în consecință, solicit", "solicit să se dispună", "solicit să se oblige", "solicit să se constate", "solicit să se oblige pârâtul la plata sumei de", etc.""",
    
    'isReclamant': """Extrage informațiile despre reclamant din documentul de mai jos (partea care inițiază procesul, fie o persoană, fie o entitate precum o instituție sau o persoană juridică). De obicei se regăsește în apropierea cuvântului "subsemnatul/a". Ne interesează doar numele complet.""",
    
    'isParat': """Extrage informațiile despre pârât din documentul de mai jos (partea împotriva căreia se face cererea; pot fi mai multe părți, fie persoane fizice, fie entități precum instituții sau persoane juridice) - ne interesează doar numele complet."""
}

SUBPOENA_SUMMARY_PROMPTS = {
    'isTemei': """Corecteaza textul temeiului legal dacă este cazul, acesta ar trebui să fie la persoana a III-a, forma pasivă, timpul perfect compus și este introdus prin "În drept".
De exemplu, "În drept, au fost invocate următoarele prevederi...". Vei răspunde doar cu textul corectat, fără alte explicații.""",
    
    'isProba': """Corectează textul probei dacă este cazul, acesta ar trebui să fie la persoana a III-a, forma pasivă, timpul perfect compus și este introdus prin "În probațiune,".
Vei răspunde doar cu textul corectat, fără alte explicații.""",

    'isSelected': """Rezumă descrierea faptelor și circumstanțelor descrise de reclamant în textul extras de mai sus, care să cuprindă toate argumentele esențiale.
Rezumatul va trebui scris la persoana a III-a, forma activă, modul indicativ și timpul perfect compus. Stilul este juridic, formal, clar și concis.
Textul va fi structurat in paragrafe, fiecare corespunzând unei idei principale. 
Pentru a reflecta clar poziția procesuală a părții, fiecare paragraf argumentativ (idee principală) va utiliza expresii de juridice precum „A arătat că”, „A susținut că”, „A învederat că”, „A menționat că”, „A expus faptul că”, „A relatat că”.
Textul va fi introdus prin „În motivare,”.
Vei răspunde doar cu textul rezumat, fără alte explicații.""",

    'isCerere': """Corecteaza textul cererii de mai sus dacă este cazul, acesta ar trebui să fie la persoana a III-a, forma activa, timpul trecut, perfect compus cu diacritice. Vor fi folosite pronume demonstrative, persoana a III-a, (e.g., acestora, acestuia). De exemplu, noastră se va transforma in acestora.
Cine a scris cererea: "{isReclamant}". 
Textul corectat va incepe mereu cu „a solicitat" sau „au solicitat". Pentru un reclamant (e.g. un singur nume de persoana, companie, institutie), va incepe cu "a solicitat", pentru mai multi reclamanti cu "au solicitat".
Vei răspunde doar cu textul corectat, fără alte explicații.""",

    'isReclamant': """Textul de mai sus conține mai multe nume de persoane/instituții/companii. De obicei numele o sa fie deja separate prin "si". Nu vrei alterna ordinea cuvintelor. Vreau să le formatezi pentru a avea o listă clară, separată prin virgulă. Vei răspunde doar cu lista, fără alte explicații.""",

    'isParat': """Textul de mai sus conține mai multe nume de persoane/instituții/companii. Vreau să le formatăm pentru a avea o listă clară, separată prin virgulă. Vei răspunde doar cu lista, fără alte explicații.""",
}

def get_subpoena_annotation_prompts() -> dict:
    """Get annotation prompts for subpoena document type"""
    return SUBPOENA_ANNOTATE_PROMPTS

def get_subpoena_summary_prompts() -> dict:
    """Get summary prompts for subpoena document type"""
    return SUBPOENA_SUMMARY_PROMPTS

def get_subpoena_annotation_system_prompt() -> str:
    """Get annotation system prompt for subpoena document type"""
    return SUBPOENA_ANNOTATION_SYSTEM_PROMPT

def get_subpoena_summary_system_prompt() -> str:
    """Get summary system prompt for subpoena document type"""
    return SUBPOENA_SUMMARY_SYSTEM_PROMPT

def get_subpoena_annotation_model_config() -> dict:
    """Get annotation model configuration for subpoena document type"""
    return SUBPOENA_ANNOTATION_MODEL_CONFIG

def get_subpoena_summary_model_config() -> dict:
    """Get summary model configuration for subpoena document type"""
    return SUBPOENA_SUMMARY_MODEL_CONFIG