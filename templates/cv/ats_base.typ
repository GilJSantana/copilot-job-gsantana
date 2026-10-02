// CV de uma coluna otimizado para ATS (Applicant Tracking Systems).
//
// Dados: JSON em `sys.inputs.cv` (enviado pelo gerador de PDF). Sem ele, usa
// ats_base.example.json, o que permite editar o template direto no Typst:
//   typst compile templates/cv/ats_base.typ
//
// Regras de ATS seguidas aqui:
//   * uma coluna, sem tabelas, ícones, imagens ou caixas de texto;
//   * contato no corpo, não em cabeçalho/rodapé (muitos ATS os ignoram);
//   * títulos de seção padrão, que os parsers reconhecem;
//   * sem hifenização (não quebra palavras-chave) e sem ligaduras
//     ("fi", "fl" extraídos como letras comuns);
//   * datas em formato único (MM/AAAA) e metadados do PDF preenchidos.
//
// Valores do JSON entram como texto puro: caracteres como #, *, _ ou $ vindos
// do histórico nunca são interpretados como marcação.

#let data = if "cv" in sys.inputs {
  json(bytes(sys.inputs.cv))
} else {
  json("ats_base.example.json")
}

#let labels = (
  pt: (
    summary: "Resumo profissional",
    experience: "Experiência profissional",
    skills: "Competências",
    education: "Formação acadêmica",
    certifications: "Certificações",
    languages: "Idiomas",
    present: "Atual",
  ),
  en: (
    summary: "Professional Summary",
    experience: "Professional Experience",
    skills: "Skills",
    education: "Education",
    certifications: "Certifications",
    languages: "Languages",
    present: "Present",
  ),
)
#let t = labels.at(data.lang)

#let get(dict, key) = dict.at(key, default: none)
#let filled(value) = value != none and value != "" and value != ()

#let month-year(value) = if value == none { t.present } else {
  value.slice(5, 7) + "/" + value.slice(0, 4)
}
#let period(item) = month-year(item.start) + " – " + month-year(get(item, "end"))

// --- Documento ---------------------------------------------------------------

#set document(
  title: data.name + " — " + data.headline,
  author: data.name,
  keywords: data.at("keywords", default: ()),
)
#set page(paper: "a4", margin: (x: 1.8cm, y: 1.6cm))
#set text(
  // prefere sans-serif comuns; Libertinus Serif vem embutida no Typst e garante a compilação
  font: ("Carlito", "Liberation Sans", "Arial", "Helvetica", "Libertinus Serif"),
  size: 10.5pt,
  lang: data.lang,
  hyphenate: false,
  ligatures: false,
)
#set par(justify: false, leading: 0.6em, spacing: 0.9em)
#set list(indent: 0.4em, body-indent: 0.5em, spacing: 0.55em)

#show heading.where(level: 1): set text(size: 18pt, weight: "bold")
#show heading.where(level: 1): set block(below: 0.4em)
#show heading.where(level: 2): it => block(above: 1.2em, below: 0.6em, sticky: true)[
  #text(size: 11pt, weight: "bold", upper(it.body))
  #v(-0.6em)
  #line(length: 100%, stroke: 0.5pt + luma(120))
]

// --- Identificação -----------------------------------------------------------

= #data.name

#text(size: 11.5pt, data.headline)

#let contact = get(data, "contact")
#if contact != none {
  let items = ("email", "phone", "location", "linkedin", "github", "website")
    .map(key => get(contact, key))
    .filter(filled)
  if items.len() > 0 { items.join("  |  ") }
}

// --- Seções ------------------------------------------------------------------

#if filled(get(data, "summary")) [
  == #t.summary
  #data.summary
]

#if filled(get(data, "skills")) [
  == #t.skills
  #data.skills.join(", ")
]

#if filled(get(data, "experiences")) [
  == #t.experience
  #for exp in data.experiences {
    block(above: 1em, breakable: true)[
      #strong(exp.title) — #exp.company #h(1fr) #period(exp)
      #if filled(get(exp, "location")) [ \ #text(fill: luma(70), exp.location)]
      #list(..exp.highlights)
    ]
  }
]

#if filled(get(data, "education")) [
  == #t.education
  #for edu in data.education [
    #strong(edu.degree) — #edu.institution #h(1fr) #period(edu) \
  ]
]

#if filled(get(data, "certifications")) [
  == #t.certifications
  #for cert in data.certifications [
    #cert.name#if filled(get(cert, "issuer")) [ — #cert.issuer]#if filled(get(cert, "year")) [ (#cert.year)] \
  ]
]

#if filled(get(data, "languages")) [
  == #t.languages
  #data.languages.join(", ")
]
