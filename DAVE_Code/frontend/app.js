let uploadedFilename = null;
let isProcessing = false;

const fileInput = document.getElementById('file-input');
const uploadBtn = document.getElementById('upload-btn');
const uploadStatus = document.getElementById('upload-status');
const statusText = document.getElementById('status-text');
const textSection = document.getElementById('text-section');
const extractedText = document.getElementById('extracted-text');
const charCount = document.getElementById('char-count');
const processTime = document.getElementById('process-time');
const validationSection = document.getElementById('validation-section');
const expiryDate = document.getElementById('expiry-date');
const docStatus = document.getElementById('doc-status');
const daysInfo = document.getElementById('days-info');
const daysText = document.getElementById('days-text');
const statusBadge = document.getElementById('status-badge');

document.addEventListener('DOMContentLoaded', function() {

    const isLoggedIn = sessionStorage.getItem('isLoggedIn');
    if (!isLoggedIn) {
        window.location.href = 'login.html';
        return;
    }
    
    const userEmail = sessionStorage.getItem('userEmail');
    const logoutLink = document.getElementById('logout-link');
    if (userEmail && logoutLink) {
        logoutLink.textContent = userEmail;
    }
    
    if (logoutLink) {
        logoutLink.addEventListener('click', function(e) {
            e.preventDefault();
            sessionStorage.removeItem('isLoggedIn');
            sessionStorage.removeItem('userEmail');
            window.location.href = 'login.html';
        });
    }

    fileInput.addEventListener('change', handleFileSelect);
    
    uploadBtn.addEventListener('click', handleUpload);
});

function handleFileSelect(event) {
    const file = event.target.files[0];
    
    if (!file) {
        uploadBtn.disabled = true;
        return;
    }
    
    const validTypes = ['image/jpeg', 'image/jpg', 'image/png', 'application/pdf'];
    if (!validTypes.includes(file.type)) {
        showUploadStatus('Invalid file type. Please select a JPEG, JPG, PNG, or PDF file.', 'error');
        uploadBtn.disabled = true;
        fileInput.value = '';
        return;
    }
    
    const maxSize = 6 * 1024 * 1024; 
    if (file.size > maxSize) {
        showUploadStatus('File too large. Maximum size is 6MB.', 'error');
        uploadBtn.disabled = true;
        fileInput.value = '';
        return;
    }
    
    showUploadStatus(`Selected: ${file.name} (${formatFileSize(file.size)})`, 'info');
    uploadBtn.disabled = false;
}

async function handleUpload() {
    const file = fileInput.files[0];
    
    if (!file) {
        alert('Please select a file first.');
        return;
    }
    
    clearPreviousResults();
    
    uploadBtn.disabled = true;
    isProcessing = true;
    
    showUploadStatus('Uploading document...', 'loading');
    
    try {
        const formData = new FormData();
        formData.append('file', file);

        const response = await fetch('http://localhost:8000/api/upload', {
            method: 'POST',
            body: formData
        });
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'Upload failed');
        }
        
        const data = await response.json();
        uploadedFilename = data.filename;
        
        showUploadStatus('Upload successful! Processing document...', 'success');
        
        await processDocument(uploadedFilename);
        
    } catch (error) {
        console.error('Upload error:', error);
        showUploadStatus('Upload failed. Please try again.', 'error');
    } finally {
        if (!uploadedFilename) {
            uploadBtn.disabled = false;
            isProcessing = false;
        }
    }
}

function showUploadStatus(message, type = 'info') {
    uploadStatus.style.display = 'block';
    
    const messageBox = uploadStatus.querySelector('.message-box');
    if (messageBox) {
        messageBox.className = 'message-box';
        
        switch(type) {
            case 'success':
                messageBox.classList.add('success-alert');
                break;
            case 'error':
                messageBox.classList.add('error-alert');
                break;
            case 'loading':
                messageBox.classList.add('info-alert');
                break;
            default:
                messageBox.classList.add('default-alert');
        }
    }
    
    statusText.textContent = message;
}

async function processDocument(filename) {
    console.log('Processing document:', filename);
    
    showUploadStatus('Processing document with OCR...', 'loading');
    
    try {
        const response = await fetch('http://localhost:8000/api/process', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ filename: filename })
        });
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'Processing failed');
        }
        
        const data = await response.json();
        displayResults(data);
        
    } catch (error) {
        console.error('Processing error:', error);
        showUploadStatus('Processing failed. Please try again.', 'error');
        uploadBtn.disabled = false;
        isProcessing = false;
    }
}

function displayResults(data) {
    textSection.style.display = 'block';
    
    extractedText.value = data.extracted_text || 'No text extracted';
    
    charCount.textContent = data.extracted_text ? data.extracted_text.length : 0;
    
    processTime.textContent = data.processing_time || '0';
    
    if (data.expiry_date) {
        displayValidationResults(data);
    }
    
    updateStatusBadge(data.is_valid);
    
    showUploadStatus('Processing complete!', 'success');
}

function displayValidationResults(data) {
    validationSection.style.display = 'block';

    if (data.expiry_date) {
        expiryDate.textContent = data.expiry_date;
    } else {
        expiryDate.textContent = 'Not detected';
    }
    
    docStatus.innerHTML = '';
    if (data.is_valid === true) {
        docStatus.innerHTML = '<span class="status-badge badge-valid normal-text">Valid</span>';
        
        if (data.days_remaining) {
            daysInfo.style.display = 'block';
            daysText.textContent = `Valid for ${data.days_remaining} more days`;
            daysText.className = 'no-margin valid-text';
        }
    } else if (data.is_valid === false) {
        docStatus.innerHTML = '<span class="status-badge badge-expired normal-text">Expired</span>';

        if (data.days_expired) {
            daysInfo.style.display = 'block';
            daysText.textContent = `Expired ${data.days_expired} days ago`;
            daysText.className = 'no-margin expired-text';
        }
    } else {
        docStatus.innerHTML = '<span class="status-badge badge-pending normal-text">Unable to validate</span>';
    }
}

function updateStatusBadge(isValid) {
    if (isValid === true) {
        statusBadge.className = 'status-badge badge-valid';
        statusBadge.textContent = 'Valid';
    } else if (isValid === false) {
        statusBadge.className = 'status-badge badge-expired';
        statusBadge.textContent = 'Expired';
    } else {
        statusBadge.className = 'status-warning';
        statusBadge.textContent = 'Pending - ID Document Required';
    }
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}

function clearPreviousResults() {
    textSection.style.display = 'none';
    validationSection.style.display = 'none';
    daysInfo.style.display = 'none';
    
    extractedText.value = '';
    charCount.textContent = '0';
    processTime.textContent = '0';
    expiryDate.textContent = '';
    docStatus.innerHTML = '';
    daysText.textContent = '';
    
    statusBadge.className = 'status-warning';
    statusBadge.textContent = 'Pending - ID Document Required';
    
    uploadedFilename = null;
}

function formatDate(dateString) {
    const date = new Date(dateString);
    const options = { year: 'numeric', month: 'long', day: 'numeric' };
    return date.toLocaleDateString('en-IE', options);
}

console.log('app.js loaded successfully');