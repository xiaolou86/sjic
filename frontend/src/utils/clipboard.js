export function copyText(text) {
  const value = String(text || '');
  if (!value) {
    return Promise.reject(new Error('empty'));
  }

  if (navigator.clipboard && window.isSecureContext) {
    return navigator.clipboard.writeText(value).catch(() => copyTextFallback(value));
  }
  return copyTextFallback(value);
}

function copyTextFallback(value) {
  return new Promise((resolve, reject) => {
    const textarea = document.createElement('textarea');
    textarea.value = value;
    textarea.setAttribute('readonly', '');
    textarea.style.position = 'fixed';
    textarea.style.top = '0';
    textarea.style.left = '0';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    textarea.setSelectionRange(0, value.length);
    let ok = false;
    try {
      ok = document.execCommand('copy');
    } catch (e) {
      ok = false;
    }
    document.body.removeChild(textarea);
    if (ok) resolve();
    else reject(new Error('copy failed'));
  });
}
