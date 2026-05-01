let appId      = null;
let appData    = null;
let appType    = null;   // full application-type doc (has form_fields)

// Polling attempt counters
let checklistPollAttempts = 0;
let documentsPollAttempts = 0;
const MAX_POLL_ATTEMPTS = 10;

document.addEventListener('DOMContentLoaded', async () => {
    if (!requireAuth()) return;

    const params = new URLSearchParams(window.location.search);
    appId = params.get('id');
    if (!appId) { window.location.href = 'index.html'; return; }

    document.getElementById('logout-btn').addEventListener('click', e => { e.preventDefault(); apiLogout(); });
    document.getElementById('edit-btn').addEventListener('click', startEdit);
    document.getElementById('save-btn').addEventListener('click', saveForm);
    document.getElementById('cancel-btn').addEventListener('click', cancelEdit);
    document.getElementById('file-input').addEventListener('change', onFileSelect);
    document.getElementById('upload-btn').addEventListener('click', uploadDocument);

    await loadApplication();
});

async function loadApplication() {
    try {
        const user = getUser();
        let url = `/api/applications/${appId}`;
        if (user && (user.role === 'admin' || user.role === 'super_admin')) {
            url = `/api/admin/applications/${appId}`;
        }
        const res = await apiFetch(url);
        if (!res.ok) { window.location.href = 'index.html'; return; }
        appData = await res.json();

        await loadAppType();
        renderSummary();
        renderFormView();

        checklistPollAttempts = 0;
        documentsPollAttempts = 0;
        await Promise.all([loadChecklist(), loadDocuments(), loadAiSuggestions()]);

        document.getElementById('loading-section').style.display = 'none';
        document.getElementById('content-section').style.display = 'block';
    } catch (e) {
        if (e.message !== 'Session expired')
            document.getElementById('loading-section').innerHTML =
                '<span class="error-alert">Could not load application.</span>';
    }
}

async function loadAppType() {
    try {
        const res = await apiFetch(`/api/application-types/${appData.application_type_id}`);
        if (res.ok) appType = await res.json();
    } catch {}
}

function _formHasIdentityFields() {
    if (!appType?.form_fields) return true;
    const identityFields = ['full_name', 'date_of_birth'];
    const requiredIdentity = appType.form_fields.filter(
        f => identityFields.includes(f.field_name) && f.is_required
    );
    if (!requiredIdentity.length) return true;
    const saved = appData?.form_data || {};
    return requiredIdentity.every(
        f => saved[f.field_name] && String(saved[f.field_name]).trim() !== ''
    );
}

function _updateUploadNotices() {
    const missing = !_formHasIdentityFields();
    const msg = missing
        ? '<div class="login-message error-alert" style="margin-bottom:0.75em">'
          + '<strong>Fill in and save the form first.</strong> '
          + 'Name and date of birth are required to verify that uploaded documents belong to you.'
          + '</div>'
        : '';

    const uploadNotice = document.getElementById('upload-form-notice');
    if (uploadNotice) {
        uploadNotice.innerHTML = msg;
        uploadNotice.style.display = missing ? 'block' : 'none';
    }
    const clNotice = document.getElementById('checklist-notice');
    if (clNotice) {
        clNotice.innerHTML = msg;
        clNotice.style.display = missing ? 'block' : 'none';
    }
}

function renderSummary() {
    document.title = `DAVE - ${appData.case_id}`;
    document.getElementById('app-page-title').textContent = `Application - ${appData.case_id}`;
    document.getElementById('case-id').textContent       = appData.case_id;
    document.getElementById('app-type').textContent      = appData.application_type_name || '-';
    document.getElementById('app-status').innerHTML      = statusBadgeHtml(appData.status);
    document.getElementById('created-at').textContent    = formatDate(appData.created_at);
    document.getElementById('updated-at').textContent    = formatDate(appData.updated_at);
    document.getElementById('submitted-at').textContent  = formatDate(appData.submitted_at);

    if (appData.admin_notes) {
        document.getElementById('admin-notes').textContent = appData.admin_notes;
        document.getElementById('admin-notes-row').style.display = 'block';
    }

    const actions = document.getElementById('app-actions');
    const editableStatuses = ['draft', 'pending', 'ready'];
    if (appData.is_editable && editableStatuses.includes(appData.status)) {
        const readyTip = appData.status !== 'ready'
            ? ' title="Form has validation errors - fix them before submitting"' : '';
        actions.innerHTML = `<button id="submit-btn" class="success-button">Submit Application</button>`;
        document.getElementById('submit-btn').addEventListener('click', submitApplication);
        document.getElementById('edit-btn').style.display = 'inline-block';
        const uploadSec = document.getElementById('upload-section');
        if (uploadSec) uploadSec.style.display = 'block';
        _updateUploadNotices();
    } else {
        actions.innerHTML = '';
        document.getElementById('edit-btn').style.display = 'none';
        const uploadSec = document.getElementById('upload-section');
        if (uploadSec) uploadSec.style.display = 'none';
    }
}

function renderFormView() {
    const fields = (appType?.form_fields || []).sort((a, b) => (a.order || 0) - (b.order || 0));
    const data   = appData?.form_data || {};
    const view   = document.getElementById('form-view');

    if (!fields.length && !Object.keys(data).length) {
        view.innerHTML = '<p style="color:#666">No form data yet. Click Edit to fill in the form.</p>';
        return;
    }

    const rows = fields.length
        ? fields
        : Object.keys(data).map(k => ({ field_name: k, label: k }));

    view.innerHTML = `<table class="info-table">
        ${rows.map(f => `
        <tr>
            <td class="label">${escapeHtml(f.label || f.field_name)}:</td>
            <td>${escapeHtml(String(data[f.field_name] ?? '-'))}</td>
        </tr>`).join('')}
    </table>`;
}

function buildInput(f, currentValue) {
    const name = escapeHtml(f.field_name);
    const val  = currentValue == null ? '' : String(currentValue);

    if (f.field_type === 'dropdown' && Array.isArray(f.options)) {
        // Always include a blank placeholder as the first option so the browser
        // never silently submits the first real option when the user hasn't chosen yet.
        const placeholder = val ? '' : `<option value="" disabled selected>- Select -</option>`;
        return `<select class="form-input" name="${name}">
            ${placeholder}
            ${f.options.map(o => `<option value="${escapeHtml(o)}"${val === o ? ' selected' : ''}>${escapeHtml(o)}</option>`).join('')}
        </select>`;
    }
    const typeMap = { date: 'date', number: 'number', email: 'email', phone: 'tel' };
    const t = typeMap[f.field_type] || 'text';
    return `<input type="${t}" class="form-input" name="${name}" value="${escapeHtml(val)}">`;
}

function startEdit() {
    const fields = (appType?.form_fields || []).sort((a, b) => (a.order || 0) - (b.order || 0));
    const data   = appData?.form_data || {};
    const rows   = fields.length
        ? fields
        : Object.keys(data).map(k => ({ field_name: k, label: k, field_type: 'text' }));

    document.getElementById('form-edit').innerHTML = rows.map(f => {
        const req  = f.is_required ? '<span style="color:#dc3545"> *</span>' : '';
        const help = f.help_text   ? `<small class="help-text">${escapeHtml(f.help_text)}</small>` : '';
        return `<div class="form-group">
            <label class="input-label">${escapeHtml(f.label || f.field_name)}${req}</label>
            ${buildInput(f, data[f.field_name])}
            ${help}
        </div>`;
    }).join('');

    document.getElementById('form-view').style.display = 'none';
    document.getElementById('form-edit').style.display = 'block';
    document.getElementById('edit-btn').style.display   = 'none';
    document.getElementById('save-btn').style.display   = 'inline-block';
    document.getElementById('cancel-btn').style.display = 'inline-block';
    document.getElementById('form-msg').style.display   = 'none';
}

function cancelEdit() {
    document.getElementById('form-edit').style.display = 'none';
    document.getElementById('form-view').style.display = 'block';
    document.getElementById('edit-btn').style.display   = 'inline-block';
    document.getElementById('save-btn').style.display   = 'none';
    document.getElementById('cancel-btn').style.display = 'none';
    document.getElementById('form-msg').style.display   = 'none';
}

async function saveForm() {
    const form_data = {};
    document.getElementById('form-edit').querySelectorAll('[name]')
        .forEach(el => {
            // Skip blank placeholder selections — don't overwrite a previously saved value
            if (el.tagName === 'SELECT' && el.value === '') return;
            form_data[el.name] = el.value;
        });
    try {
        const res = await apiFetch(`/api/applications/${appId}`, {
            method: 'PATCH',
            body: JSON.stringify({ form_data }),
        });
        if (!res.ok) {
            const err = await res.json();
            showFormMsg(err.detail || 'Save failed.', 'error');
            return;
        }
        appData = await res.json();
        renderFormView();
        cancelEdit();
        document.getElementById('updated-at').textContent = formatDate(appData.updated_at);
        // Refresh checklist, documents and AI suggestions — form changes alter required docs
        // and trigger background re-validation of already-processed documents.
        await Promise.all([loadChecklist(), loadDocuments(), loadAiSuggestions()]);
        _updateUploadNotices();
    } catch (e) {
        if (e.message !== 'Session expired') showFormMsg('Could not save.', 'error');
    }
}

function showFormMsg(msg, type) {
    const el = document.getElementById('form-msg');
    el.textContent   = msg;
    el.className     = 'login-message ' + (type === 'success' ? 'success-alert' : 'error-alert');
    el.style.display = 'block';
}

async function submitApplication() {
    if (!confirm('Submit this application? You will not be able to edit it afterwards.')) return;
    try {
        const res = await apiFetch(`/api/applications/${appId}/submit`, { method: 'POST' });
        if (!res.ok) {
            const err = await res.json();
            const detail = err.detail;
            const msg = typeof detail === 'string'
                ? detail
                : (Array.isArray(detail?.errors) ? detail.errors.join('; ') : 'Submission failed.');
            alert(msg);
            return;
        }
        appData = await res.json();
        renderSummary();
    } catch {}
}


async function loadChecklist() {
    const loadEl = document.getElementById('checklist-loading');
    const listEl = document.getElementById('checklist-list');
    try {
        const res = await apiFetch(`/api/applications/${appId}/document-checklist`);
        loadEl.style.display = 'none';
        if (!res.ok) { listEl.innerHTML = '<p style="color:#666">Could not load checklist.</p>'; return; }
        const data = await res.json();
        if (!data.items?.length) {
            listEl.innerHTML = '<p style="color:#666">No required documents specified for this application type.</p>';
            return;
        }
        listEl.innerHTML = data.items.map((item, idx) => {
            const valBadge  = _validationBadge(item.validation_result);
            const condLabel = item.is_conditional && item.condition_label
                ? `<div class="small-text condition-label">📋 ${escapeHtml(item.condition_label)}</div>`
                : '';
            const inputId   = `cl-file-${idx}`;
            const safeType  = escapeHtml(item.document_type);

            let uploadOrDoc = '';
            if (item.uploaded) {
                const terminalCl = ['validated', 'validated_with_issues', 'processing_failed'];
                const isProcessing = !terminalCl.includes(item.status);
                const statusColor = (item.status === 'validated') ? '#198754'
                    : (item.status === 'validated_with_issues') ? '#fd7e14'
                    : (item.status === 'processing_failed') ? '#dc3545'
                    : '#555';
                const statusText = statusLabel(item.status || 'processing');
                const stageBlock = isProcessing ? _processingStageHtml(item.processing_step, item.status) : '';
                uploadOrDoc = `
                    <div class="cl-doc-row">
                        <span class="small-text" style="color:${statusColor}">
                            ${isProcessing ? '⏳' : 'Uploaded'} - ${statusText}
                        </span>
                        ${stageBlock}
                        ${valBadge}
                        <div class="cl-doc-actions">
                            <button onclick="downloadDoc('${escapeHtml(item.document_id)}')"
                                class="secondary-button"
                                style="padding:0.25em 0.6em;font-size:0.78rem">
                            Download
                        </button>
                            ${appData?.is_editable ? `
                            <button onclick="deleteChecklistDoc('${escapeHtml(item.document_id)}')"
                                    class="danger-button"
                                    style="padding:0.25em 0.6em;font-size:0.78rem;margin-left:0.3em">
                                Delete
                            </button>` : ''}
                        </div>
                    </div>`;
            } else if (appData?.is_editable) {
                uploadOrDoc = `
                    <div class="cl-upload-row" style="margin-top:0.5em">
                        <label class="cl-file-label" for="${inputId}">
                            <span class="cl-file-text" id="cl-fname-${idx}">Choose file…</span>
                        </label>
                        <input type="file" id="${inputId}"
                               accept=".pdf,.jpg,.jpeg,.png"
                               style="display:none"
                               onchange="onClFileSelect(this, ${idx})">
                        <button id="cl-btn-${idx}"
                                class="primary-button"
                                style="padding:0.25em 0.75em;font-size:0.82rem;margin-left:0.4em"
                                disabled
                                onclick="uploadChecklistDoc('${safeType}', '${inputId}', ${idx})">
                            Upload
                        </button>
                        <div id="cl-msg-${idx}" class="login-message" style="display:none;margin-top:0.4em;font-size:0.82rem"></div>
                    </div>`;
            }

            return `
            <div class="checklist-item ${item.uploaded ? 'checklist-done' : 'checklist-pending'}" id="cl-item-${idx}">
                <span class="checklist-icon">${item.uploaded ? '✅' : (item.is_mandatory ? '❗' : '⭕')}</span>
                <div class="checklist-info" style="flex:1">
                    <div>
                        <strong>${safeType}</strong>
                        ${item.is_mandatory
                            ? '<span class="req-badge">Required</span>'
                            : '<span class="opt-badge">Optional</span>'}
                        ${item.is_conditional ? '<span class="cond-badge">Conditional</span>' : ''}
                    </div>
                    ${condLabel}
                    ${item.description ? `<div class="small-text">${escapeHtml(item.description)}</div>` : ''}
                    ${uploadOrDoc}
                </div>
            </div>`;
        }).join('');

        // Poll every 3 seconds while any item is in a non-terminal state
        // ("processing" = OCR running; "processed" = OCR done, validation in progress)
        const terminalStatuses = ['validated', 'validated_with_issues', 'processing_failed'];
        const stillProcessing = data.items.some(
            i => i.uploaded && !terminalStatuses.includes(i.status)
        );
        if (stillProcessing) {
            checklistPollAttempts++;
            if (checklistPollAttempts < MAX_POLL_ATTEMPTS) {
                setTimeout(() => loadChecklist(), 3000);
            } else {
                listEl.innerHTML += '<div style="color:#b85c00;margin-top:1em">Processing is taking longer than expected. Please refresh the page or try again later.</div>';
            }
        } else {
            checklistPollAttempts = 0;
        }
    } catch {
        loadEl.style.display = 'none';
        listEl.innerHTML = '<p style="color:#666">Could not load checklist.</p>';
    }
}

function onClFileSelect(input, idx) {
    const btn   = document.getElementById(`cl-btn-${idx}`);
    const msgEl = document.getElementById(`cl-msg-${idx}`);
    const label = document.getElementById(`cl-fname-${idx}`);
    msgEl.style.display = 'none';
    const file = input.files[0];
    if (!file) { btn.disabled = true; label.textContent = 'Choose file…'; return; }
    const valid = ['image/jpeg', 'image/jpg', 'image/png', 'application/pdf'];
    if (!valid.includes(file.type)) {
        msgEl.textContent = 'Invalid type. Use PDF, JPG or PNG.';
        msgEl.className   = 'login-message error-alert';
        msgEl.style.display = 'block';
        btn.disabled = true; label.textContent = 'Choose file…'; return;
    }
    if (file.size > 10 * 1024 * 1024) {
        msgEl.textContent = 'File too large (max 10 MB).';
        msgEl.className   = 'login-message error-alert';
        msgEl.style.display = 'block';
        btn.disabled = true; label.textContent = 'Choose file…'; return;
    }
    label.textContent = file.name;
    btn.disabled = false;
}

async function uploadChecklistDoc(docType, inputId, idx) {
    if (!_formHasIdentityFields()) {
        const msgEl = document.getElementById(`cl-msg-${idx}`);
        msgEl.textContent   = 'Please fill in and save the form before uploading documents.';
        msgEl.className     = 'login-message error-alert';
        msgEl.style.display = 'block';
        return;
    }
    const file  = document.getElementById(inputId)?.files[0];
    const btn   = document.getElementById(`cl-btn-${idx}`);
    const msgEl = document.getElementById(`cl-msg-${idx}`);
    if (!file) return;

    btn.disabled    = true;
    btn.textContent = 'Uploading…';

    const formData = new FormData();
    formData.append('file', file);
    formData.append('document_type', docType);

    try {
        const res = await apiFetch(`/api/applications/${appId}/documents`, {
            method: 'POST',
            body: formData,
        });
        if (!res.ok) {
            const err = await res.json();
            msgEl.textContent   = err.detail || 'Upload failed.';
            msgEl.className     = 'login-message error-alert';
            msgEl.style.display = 'block';
            btn.textContent = 'Upload';
            btn.disabled    = false;
        } else {
            await Promise.all([loadChecklist(), loadDocuments()]);
        }
    } catch (e) {
        if (e.message !== 'Session expired') {
            msgEl.textContent   = 'Upload failed.';
            msgEl.className     = 'login-message error-alert';
            msgEl.style.display = 'block';
            btn.textContent = 'Upload';
            btn.disabled    = false;
        }
    }
}

async function deleteChecklistDoc(docId) {
    if (!confirm('Delete this document? This cannot be undone.')) return;
    try {
        const res = await apiFetch(`/api/documents/${docId}`, { method: 'DELETE' });
        if (res.ok || res.status === 204) {
            await loadChecklist();
        } else {
            alert('Could not delete document.');
        }
    } catch {}
}

function _validationBadge(v) {
    if (!v) return '';

    // Passport photos are face photographs — no text validation applies.
    if (v.skip_reason === 'passport_photo') {
        return `<div class="val-badge val-ok">✔ Photo received - no document validation required</div>`;
    }
    const issues = v.issues?.length
        ? `<ul style="margin:0.2em 0 0 1em;padding:0;font-size:0.78rem;color:#842029">${v.issues.map(i => `<li>${escapeHtml(i)}</li>`).join('')}</ul>`
        : (v.overall_valid === false
            ? '<div style="font-size:0.78rem;color:#842029;margin-top:0.2em">No further details stored - delete and re-upload the document to re-run validation.</div>'
            : '');

    // OpenAI summary + verified fields
    const aiSummary = v.ai_summary
        ? `<div style="margin-top:0.3em;font-size:0.78rem;color:#555;font-style:italic">🤖 ${escapeHtml(v.ai_summary)}</div>`
        : '';
    const aiFields = v.ai_verified_fields && Object.keys(v.ai_verified_fields).length
        ? `<div style="margin-top:0.2em;font-size:0.75rem;color:#2d6a4f">✔ AI verified: ${Object.entries(v.ai_verified_fields).map(([k,val]) => `<b>${escapeHtml(k)}</b>: ${escapeHtml(String(val))}`).join(' · ')}</div>`
        : '';

    // HuggingFace type check
    let hfTypeHtml = '';
    if (v.hf_type_verified === true) {
        const pct = v.hf_type_confidence != null ? ` (${Math.round(v.hf_type_confidence * 100)}%)` : '';
        hfTypeHtml = `<div style="margin-top:0.3em;font-size:0.78rem;color:#2d6a4f">Document type confirmed${pct}</div>`;
    } else if (v.hf_type_verified === false) {
        const detected = v.hf_detected_as ? ` - looks like: <em>${escapeHtml(v.hf_detected_as)}</em>` : '';
        hfTypeHtml = `<div style="margin-top:0.3em;font-size:0.78rem;color:#842029">Type mismatch${detected}</div>`;
    }

    // HuggingFace extracted fields
    let hfFieldsHtml = '';
    if (v.hf_extracted_fields && Object.keys(v.hf_extracted_fields).length) {
        const fieldRows = Object.entries(v.hf_extracted_fields)
            .map(([k, val]) => {
                const conf = v.hf_field_confidences?.[k];
                const confStr = conf != null ? ` <span style="color:#999">(${Math.round(conf * 100)}%)</span>` : '';
                return `<b>${escapeHtml(k.replace(/_/g, ' '))}</b>: ${escapeHtml(String(val))}${confStr}`;
            }).join(' · ');
        hfFieldsHtml = `<div style="margin-top:0.2em;font-size:0.75rem;color:#0a3055">Extracted: ${fieldRows}</div>`;
    }

    if (v.overall_valid === true) {
        return `<div class="val-badge val-ok">✔ Document validated${aiSummary}${aiFields}${hfTypeHtml}${hfFieldsHtml}</div>`;
    }
    if (v.overall_valid === false) {
        return `<div class="val-badge val-fail">⚠ Validation issues${issues}${aiSummary}${hfTypeHtml}${hfFieldsHtml}</div>`;
    }
    return '';
}

async function loadAiSuggestions() {
    const panel = document.getElementById('ai-suggestions-panel');
    if (!panel) return;
    panel.innerHTML = '<p style="color:#666;font-size:0.85rem">Loading AI suggestions…</p>';
    try {
        const res = await apiFetch(`/api/applications/${appId}/ai-document-suggestions`);
        if (!res.ok) { panel.innerHTML = '<p style="color:#888;font-size:0.85rem">AI suggestions unavailable.</p>'; return; }
        const data = await res.json();
        if (!data.suggestions?.length) {
            panel.innerHTML = '<p style="color:#666;font-size:0.85rem">No additional documents suggested by AI.</p>';
            return;
        }
        panel.innerHTML = `<ul class="ai-suggestion-list">${data.suggestions.map(s => `
            <li>
                <strong>${escapeHtml(s.document_type)}</strong>
                ${s.is_mandatory ? '<span class="req-badge">Mandatory</span>' : '<span class="opt-badge">Suggested</span>'}
                <div class="small-text">${escapeHtml(s.reason)}</div>
                ${s.condition ? `<div class="small-text condition-label"> ${escapeHtml(s.condition)}</div>` : ''}
            </li>`).join('')}
        </ul>`;
    } catch {
        panel.innerHTML = '<p style="color:#888;font-size:0.85rem">AI suggestions unavailable.</p>';
    }
}

function _processingStageHtml(step, status) {
    // Maps the backend processing_step string to a user-friendly label + icon
    const stages = [
        { key: 'Downloading file',       icon: '⬇️', label: 'Downloading file' },
        { key: 'Running OCR',            icon: '🔍', label: 'Running OCR (reading text)' },
        { key: 'Extracting fields',      icon: '🧠', label: 'Extracting fields (AI / NER)' },
        { key: 'Saving OCR results',     icon: '💾', label: 'Saving results' },
        { key: 'Verifying document type',icon: '📋', label: 'Verifying document type (HuggingFace)' },
        { key: 'Comparing dates',        icon: '📅', label: 'Cross-checking dates & name' },
        { key: 'Re-validating',          icon: '🔄', label: 'Re-validating document' },
    ];
    const match = stages.find(s => step && step.startsWith(s.key));
    let icon, label;
    if (match) {
        icon  = match.icon;
        label = match.label;
    } else if (status === 'processed') {
        // OCR finished, validation pipeline running
        icon  = '📋';
        label = 'Validating document fields & type';
    } else {
        // status === 'processing' (or unknown): OCR not done yet
        icon  = '🔍';
        label = 'Running OCR (reading text)';
    }
    return `<div style="margin-top:0.4em;padding:0.35em 0.65em;background:#fff8e1;
                border-left:3px solid #f0a500;border-radius:4px;font-size:0.82rem;color:#5a4000">
        <span style="margin-right:0.4em">${icon}</span>
        <span class="processing-pulse">Current stage:</span>
        <strong style="margin-left:0.2em">${escapeHtml(label)}</strong>
    </div>`;
}

async function loadDocuments() {
    const loadEl  = document.getElementById('docs-loading');
    const emptyEl = document.getElementById('docs-empty');
    const listEl  = document.getElementById('docs-list');
    // Do NOT blank listEl here — keep existing content visible during the
    // API round-trip so the section never shows an empty flash while polling.
    emptyEl.style.display = 'none';

    try {
        const res = await apiFetch(`/api/applications/${appId}/documents`);
        loadEl.style.display = 'none';
        if (!res.ok) { listEl.innerHTML = '<p style="color:#666">Could not load documents.</p>'; return; }
        const { documents } = await res.json();
        if (!documents?.length) {
            listEl.innerHTML = '';
            emptyEl.style.display = 'block';
            return;
        }

        listEl.innerHTML = documents.map(doc => {
            const terminalStatuses = ['validated', 'validated_with_issues', 'processing_failed'];
            let statusHtml;
            if (!terminalStatuses.includes(doc.status)) {
                // Still in pipeline — show current stage prominently
                const stageBlock = _processingStageHtml(doc.processing_step, doc.status);
                statusHtml = `<span style="color:#555;font-size:0.82rem">⏳ Processing…</span>${stageBlock}`;
            } else {
                statusHtml = statusBadgeHtml(doc.status, true);
            }
            return `
            <div class="doc-item" id="doc-${escapeHtml(doc.id)}">
                <div class="doc-thumb">
                    <span style="font-size:2rem;line-height:56px;display:inline-block;width:56px;text-align:center">
                        ${doc.filename?.toLowerCase().endsWith('.pdf') ? '📄' : '🖼️'}
                    </span>
                </div>
                <div class="doc-info">
                    <div><strong>${escapeHtml(doc.filename)}</strong></div>
                    <div class="small-text">${escapeHtml(doc.document_type)} - ${formatFileSize(doc.file_size)}</div>
                    <div style="margin-top:0.25em">${statusHtml}</div>                    ${_validationBadge(doc.validation_result)}                </div>
                <div class="doc-actions">
                    <button onclick="downloadDoc('${escapeHtml(doc.id)}')"
                            class="secondary-button"
                            style="padding:0.3em 0.7em;font-size:0.8rem">
                        Download
                    </button>
                    ${appData?.is_editable ? `
                    <button onclick="deleteDocument('${escapeHtml(doc.id)}')"
                            class="danger-button"
                            style="padding:0.3em 0.7em;font-size:0.8rem;margin-left:0.3em">
                        Delete
                    </button>` : ''}
                </div>
            </div>`;
        }).join('');

        // Poll every 3 seconds while any document is still in the pipeline
        const terminalStatuses = ['validated', 'validated_with_issues', 'processing_failed'];
        const stillProcessing = documents.some(d => !terminalStatuses.includes(d.status));
        if (stillProcessing) {
            documentsPollAttempts++;
            if (documentsPollAttempts < MAX_POLL_ATTEMPTS) {
                setTimeout(() => loadDocuments(), 3000);
            } else {
                listEl.innerHTML += '<div style="color:#b85c00;margin-top:1em">Processing is taking longer than expected. Please refresh the page or try again later.</div>';
            }
        } else {
            documentsPollAttempts = 0;
        }
    } catch {
        loadEl.style.display = 'none';
        listEl.innerHTML = '<p style="color:#666">Could not load documents.</p>';
    }
}

async function downloadDoc(docId) {
    try {
        const res = await apiFetch(`/api/documents/${docId}/download`);
        if (!res.ok) { alert('Could not download document.'); return; }
        const blob = await res.blob();
        const cd   = res.headers.get('Content-Disposition') || '';
        const match = cd.match(/filename="?([^"]+)"?/);
        const filename = match ? match[1] : 'document';
        const url = URL.createObjectURL(blob);
        const a   = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    } catch {
        alert('Could not download document.');
    }
}

function onFileSelect(event) {
    const file  = event.target.files[0];
    const btn   = document.getElementById('upload-btn');
    const msgEl = document.getElementById('upload-msg');
    msgEl.style.display = 'none';
    if (!file) { btn.disabled = true; return; }
    const valid = ['image/jpeg', 'image/jpg', 'image/png', 'application/pdf'];
    if (!valid.includes(file.type)) {
        msgEl.textContent = 'Invalid file type. Use PDF, JPG, JPEG, or PNG.';
        msgEl.className   = 'login-message error-alert';
        msgEl.style.display = 'block';
        btn.disabled = true;
        return;
    }
    if (file.size > 10 * 1024 * 1024) {
        msgEl.textContent = 'File too large. Maximum size is 10 MB.';
        msgEl.className   = 'login-message error-alert';
        msgEl.style.display = 'block';
        btn.disabled = true;
        return;
    }
    btn.disabled = false;
}

async function uploadDocument() {
    const file    = document.getElementById('file-input').files[0];
    const docType = document.getElementById('doc-type-input').value.trim();
    const msgEl   = document.getElementById('upload-msg');
    const btn     = document.getElementById('upload-btn');

    if (!_formHasIdentityFields()) {
        msgEl.textContent = 'Please fill in and save the form before uploading documents.';
        msgEl.className   = 'login-message error-alert';
        msgEl.style.display = 'block';
        return;
    }

    btn.disabled    = true;
    btn.textContent = 'Uploading…';

    const formData = new FormData();
    formData.append('file', file);
    formData.append('document_type', docType);

    try {
        const res = await apiFetch(`/api/applications/${appId}/documents`, {
            method: 'POST',
            body: formData,
        });
        if (!res.ok) {
            const err = await res.json();
            msgEl.textContent   = err.detail || 'Upload failed.';
            msgEl.className     = 'login-message error-alert';
            msgEl.style.display = 'block';
        } else {
            msgEl.textContent   = 'Document uploaded. OCR processing has started in the background.';
            msgEl.className     = 'login-message success-alert';
            msgEl.style.display = 'block';
            document.getElementById('file-input').value    = '';
            document.getElementById('doc-type-input').value = '';
            btn.disabled = true;
            await Promise.all([loadDocuments(), loadChecklist()]);
        }
    } catch (e) {
        if (e.message !== 'Session expired') {
            msgEl.textContent   = 'Upload failed.';
            msgEl.className     = 'login-message error-alert';
            msgEl.style.display = 'block';
        }
    }
    btn.textContent = 'Upload';
    btn.disabled    = document.getElementById('file-input').files.length === 0;
}

async function deleteDocument(docId) {
    if (!confirm('Delete this document? This cannot be undone.')) return;
    try {
        const res = await apiFetch(`/api/documents/${docId}`, { method: 'DELETE' });
        if (res.ok || res.status === 204) {
            document.getElementById(`doc-${docId}`)?.remove();
            const listEl = document.getElementById('docs-list');
            if (!listEl.innerHTML.trim()) document.getElementById('docs-empty').style.display = 'block';
            await loadChecklist();
        } else {
            alert('Could not delete document.');
        }
    } catch {}
}
