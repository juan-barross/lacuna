const LABELS = {
  tipo: "Tipo",
  numero_contrato: "Número do contrato",
  processo: "Processo",
  contratada_nome: "Contratada",
  contratada_cnpj: "CNPJ",
  objeto: "Objeto",
  valor: "Valor",
  data_assinatura: "Data de assinatura",
};
const ICONS = {
  ok: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 8.5l3 3 7-7" fill="none" stroke="currentColor" stroke-width="2"/></svg>',
  miss: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 4l8 8M12 4l-8 8" fill="none" stroke="currentColor" stroke-width="2"/></svg>',
};
const money = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

const select = document.querySelector("#trecho");
const onlyMisses = document.querySelector("#erros");
const previous = document.querySelector("#anterior");
const next = document.querySelector("#proximo");
const position = document.querySelector("#posicao");
const source = document.querySelector("#texto");
const fieldsTable = document.querySelector("#campos");
const invalidNote = document.querySelector("#invalido");

function cell(tag, text, className = "") {
  const element = document.createElement(tag);
  element.textContent = text;
  if (className) element.className = className;
  return element;
}

function show(field, value) {
  if (value === null || value === undefined) return "—";
  if (field === "valor") return money.format(value);
  if (field === "data_assinatura") return value.split("-").reverse().join("/");
  return String(value);
}

function header(columns) {
  const row = document.createElement("tr");
  row.append(...columns.map((column) => cell("th", column)));
  const head = document.createElement("thead");
  head.append(row);
  return head;
}

function renderF1(data) {
  const names = Object.keys(data.extratores);
  const body = document.createElement("tbody");
  body.append(
    ...data.campos.map((field) => {
      const row = document.createElement("tr");
      const scores = names.map((name) => cell("td", data.f1[name][field].toFixed(2).replace(".", ","), "num"));
      row.append(cell("td", LABELS[field]), ...scores);
      return row;
    }),
  );
  document.querySelector("#f1").replaceChildren(header(["Campo", ...Object.values(data.extratores)]), body);
}

function answerCell(doc, name, field) {
  const td = document.createElement("td");
  const answer = doc.respostas[name];
  const ok = doc.acertos[name][field];
  const result = cell("span", "", `result ${ok ? "ok" : "miss"}`);
  result.innerHTML = ICONS[ok ? "ok" : "miss"];
  result.append(cell("span", show(field, answer[field]), "value-text"), cell("span", ok ? "certo" : "errado", "visually-hidden"));
  td.append(result);
  return td;
}

function renderDocument(data, doc) {
  source.textContent = doc.texto;
  const names = Object.keys(data.extratores).filter((name) => doc.respostas[name] !== null);
  const invalid = Object.keys(data.extratores).filter((name) => doc.respostas[name] === null);
  invalidNote.textContent = invalid.length
    ? `${invalid.map((name) => data.extratores[name]).join(" e ")}: JSON fora do esquema neste trecho, conta como erro em todos os campos preenchidos.`
    : "";
  invalidNote.hidden = !invalid.length;
  const body = document.createElement("tbody");
  body.append(
    ...data.campos.map((field) => {
      const row = document.createElement("tr");
      const answers = names.map((name) => answerCell(doc, name, field));
      row.append(cell("th", LABELS[field]), cell("td", show(field, doc.ouro[field])), ...answers);
      return row;
    }),
  );
  fieldsTable.replaceChildren(header(["Campo", "Resposta certa", ...names.map((name) => data.extratores[name])]), body);
}

function visible(data) {
  const missed = (doc) => Object.values(doc.acertos.qlora).some((ok) => !ok);
  return onlyMisses.checked ? data.documentos.filter(missed) : data.documentos;
}

function fillOptions(docs) {
  select.replaceChildren(
    ...docs.map((doc, i) => {
      const option = cell("option", `${i + 1}. ${doc.municipio} · ${doc.ouro.numero_contrato ?? "sem número"}`);
      option.value = doc.id;
      return option;
    }),
  );
}

function start(data) {
  renderF1(data);
  let docs = visible(data);

  function go(index) {
    const doc = docs[index];
    select.value = doc.id;
    previous.disabled = index === 0;
    next.disabled = index === docs.length - 1;
    position.textContent = `Trecho ${index + 1} de ${docs.length}`;
    renderDocument(data, doc);
  }

  const current = () => docs.findIndex((doc) => doc.id === select.value);
  select.addEventListener("change", () => go(current()));
  previous.addEventListener("click", () => go(current() - 1));
  next.addEventListener("click", () => go(current() + 1));
  onlyMisses.addEventListener("change", () => {
    docs = visible(data);
    fillOptions(docs);
    go(0);
  });
  fillOptions(docs);
  go(0);
}

fetch("dados.json")
  .then((response) => response.json())
  .then(start)
  .catch(() => {
    position.textContent = "Não foi possível carregar os dados. Recarregue a página para tentar de novo.";
  });
