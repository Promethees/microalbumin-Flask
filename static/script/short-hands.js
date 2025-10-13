// Utility short-hands
const $id = id => document.getElementById(id);
const $text = (id, text) => {
    const element = $id(id);
    if (element) {
        element.textContent = text;
    }
};
const $append = (id, text) => { $id(id).textContent += text; };
const $disable = (ids, state = true) => ids.forEach(id => $id(id).disabled = state);
const $toggleClass = (id, cls, state) => {
    const element = $id(id);
    if (element) 
        element.classList.toggle(cls, state);
}

const $qid = id => document.querySelectorAll(id)
const $toggleQueryClass = (selector, cls, state) =>
    $qid(selector).forEach(el => el.classList.toggle(cls, state));

const $hidden = (ids, state = true) => ids.forEach(id => $toggleClass(id, "hidden", state));

const getValFloat = id => parseFloat(document.getElementById(id).value);
const getValInt = id => parseInt(document.getElementById(id).value);
const getBtnChecked = id => document.getElementById(id) ? document.getElementById(id).checked : false;

function getTimeUnitValue(id = 'time-unit') {
    const element = document.getElementById(id);
    if (element && (element.style.display !== 'none' && element.style.visibility !== 'hidden')) {
        return element.value;
    }
    return null;
}

const $showText = (id, text) => {
    const el = document.getElementById(id);
    el.textContent = text;
    el.style.display = "";
};
