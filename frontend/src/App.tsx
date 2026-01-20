import React, { useState, useRef, useCallback } from 'react';
import { Upload, FileText, Loader2, CheckCircle2, AlertCircle, X, Download, Zap } from 'lucide-react';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

interface Job {
  id: string;
  file: File;
  status: 'idle' | 'uploading' | 'processing' | 'completed' | 'failed';
  progress: number;
  message: string;
  downloadUrl?: string;
}

function App() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [ocrEnabled, setOcrEnabled] = useState(true);
  const [language, setLanguage] = useState('auto');
  const fileInputRef = useRef<HTMLInputElement>(null);

  const languages = [
    { code: 'auto', name: 'Auto-detect' },
    { code: 'en', name: 'English' },
    { code: 'ru', name: 'Russian' },
    { code: 'de', name: 'German' },
    { code: 'fr', name: 'French' },
    { code: 'es', name: 'Spanish' },
    { code: 'zh', name: 'Chinese' },
    { code: 'ja', name: 'Japanese' },
    { code: 'ko', name: 'Korean' },
    { code: 'ar', name: 'Arabic' },
  ];

  const handleFiles = useCallback((files: FileList | null) => {
    if (!files) return;

    const newJobs: Job[] = Array.from(files)
      .filter(f => f.name.toLowerCase().endsWith('.pdf'))
      .map(file => ({
        id: Math.random().toString(36).substr(2, 9),
        file,
        status: 'idle',
        progress: 0,
        message: 'Ready to convert'
      }));

    setJobs(prev => [...prev, ...newJobs]);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    handleFiles(e.dataTransfer.files);
  }, [handleFiles]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const removeJob = (id: string) => {
    setJobs(prev => prev.filter(j => j.id !== id));
  };

  const processJob = async (id: string) => {
    const job = jobs.find(j => j.id === id);
    if (!job) return;

    // Update status to uploading
    setJobs(prev => prev.map(j =>
      j.id === id ? { ...j, status: 'uploading', message: 'Uploading...', progress: 10 } : j
    ));

    const formData = new FormData();
    formData.append('file', job.file);
    formData.append('ocr_enabled', String(ocrEnabled));
    formData.append('language', language);

    try {
      const response = await fetch(`${API_URL}/api/v1/convert`, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Conversion failed');
      }

      const result = await response.json();

      // If completed immediately (sync processing)
      if (result.status === 'completed') {
        setJobs(prev => prev.map(j =>
          j.id === id ? {
            ...j,
            status: 'completed',
            message: result.message || 'Conversion complete!',
            progress: 100,
            downloadUrl: `${API_URL}/api/v1/download/${result.job_id}`
          } : j
        ));
        return;
      }

      // For async processing, poll for status
      setJobs(prev => prev.map(j =>
        j.id === id ? { ...j, status: 'processing', message: 'Processing...', progress: 30 } : j
      ));

      // Poll for completion
      const pollStatus = async () => {
        const statusRes = await fetch(`${API_URL}/api/v1/jobs/${result.job_id}`);
        const statusData = await statusRes.json();

        if (statusData.status === 'completed') {
          setJobs(prev => prev.map(j =>
            j.id === id ? {
              ...j,
              status: 'completed',
              message: `Completed in ${statusData.processing_time_ms}ms`,
              progress: 100,
              downloadUrl: `${API_URL}${statusData.download_url}`
            } : j
          ));
        } else if (statusData.status === 'failed') {
          setJobs(prev => prev.map(j =>
            j.id === id ? { ...j, status: 'failed', message: statusData.message } : j
          ));
        } else {
          // Still processing
          setJobs(prev => prev.map(j =>
            j.id === id ? {
              ...j,
              progress: statusData.progress || 50,
              message: statusData.message || 'Processing...'
            } : j
          ));
          // Poll again
          setTimeout(pollStatus, 1000);
        }
      };

      pollStatus();

    } catch (error) {
      setJobs(prev => prev.map(j =>
        j.id === id ? {
          ...j,
          status: 'failed',
          message: error instanceof Error ? error.message : 'Conversion failed'
        } : j
      ));
    }
  };

  const processAll = async () => {
    const idleJobs = jobs.filter(j => j.status === 'idle');
    for (const job of idleJobs) {
      await processJob(job.id);
    }
  };

  const downloadFile = (url: string, filename: string) => {
    const a = document.createElement('a');
    a.href = url;
    a.download = filename.replace('.pdf', '.docx');
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100">
      {/* Header */}
      <header className="bg-white border-b border-slate-200 shadow-sm">
        <div className="max-w-5xl mx-auto px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-gradient-to-br from-blue-500 to-indigo-600 text-white rounded-xl shadow-lg shadow-blue-500/25">
              <FileText size={24} />
            </div>
            <div>
              <h1 className="text-xl font-bold text-slate-900">PDF to DOCX Converter</h1>
              <p className="text-sm text-slate-500">AI-powered conversion with OCR support</p>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-8">
        {/* Settings Panel */}
        <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6 mb-6">
          <div className="flex flex-wrap items-center gap-6">
            {/* OCR Toggle */}
            <div className="flex items-center gap-3">
              <label className="text-sm font-medium text-slate-700">OCR for scans</label>
              <button
                onClick={() => setOcrEnabled(!ocrEnabled)}
                className={`relative w-12 h-6 rounded-full transition-colors ${
                  ocrEnabled ? 'bg-blue-500' : 'bg-slate-300'
                }`}
              >
                <span
                  className={`absolute top-1 w-4 h-4 bg-white rounded-full transition-transform shadow ${
                    ocrEnabled ? 'left-7' : 'left-1'
                  }`}
                />
              </button>
            </div>

            {/* Language Select */}
            <div className="flex items-center gap-2">
              <label className="text-sm font-medium text-slate-700">Language</label>
              <select
                value={language}
                onChange={(e) => setLanguage(e.target.value)}
                className="bg-slate-50 border border-slate-200 text-slate-700 text-sm rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              >
                {languages.map(lang => (
                  <option key={lang.code} value={lang.code}>{lang.name}</option>
                ))}
              </select>
            </div>
          </div>
        </div>

        {/* Drop Zone */}
        <div
          onClick={() => fileInputRef.current?.click()}
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          className={`
            group relative border-2 border-dashed rounded-2xl p-12
            flex flex-col items-center justify-center text-center
            cursor-pointer transition-all bg-white
            ${isDragging
              ? 'border-blue-400 bg-blue-50'
              : 'border-slate-300 hover:border-blue-400 hover:bg-slate-50'
            }
          `}
        >
          <div className={`
            p-4 rounded-full mb-4 transition-all
            ${isDragging ? 'bg-blue-100 text-blue-600' : 'bg-slate-100 text-slate-500 group-hover:bg-blue-100 group-hover:text-blue-600'}
          `}>
            <Upload size={32} />
          </div>
          <h3 className="text-lg font-semibold text-slate-900 mb-1">
            Drop PDF files here
          </h3>
          <p className="text-sm text-slate-500">
            or click to browse • Supports batch upload
          </p>
          <input
            type="file"
            ref={fileInputRef}
            onChange={(e) => handleFiles(e.target.files)}
            accept=".pdf"
            multiple
            className="hidden"
          />
        </div>

        {/* Jobs List */}
        {jobs.length > 0 && (
          <div className="mt-6 space-y-3">
            {jobs.map(job => (
              <div
                key={job.id}
                className="bg-white border border-slate-200 rounded-xl p-4 flex items-center gap-4 shadow-sm"
              >
                {/* Icon */}
                <div className={`
                  p-3 rounded-lg shrink-0
                  ${job.status === 'completed' ? 'bg-green-100 text-green-600' : ''}
                  ${job.status === 'failed' ? 'bg-red-100 text-red-600' : ''}
                  ${job.status === 'idle' ? 'bg-slate-100 text-slate-600' : ''}
                  ${['uploading', 'processing'].includes(job.status) ? 'bg-blue-100 text-blue-600' : ''}
                `}>
                  {job.status === 'completed' && <CheckCircle2 size={20} />}
                  {job.status === 'failed' && <AlertCircle size={20} />}
                  {job.status === 'idle' && <FileText size={20} />}
                  {['uploading', 'processing'].includes(job.status) && (
                    <Loader2 size={20} className="animate-spin" />
                  )}
                </div>

                {/* Info */}
                <div className="flex-1 min-w-0">
                  <div className="font-medium text-slate-900 truncate">{job.file.name}</div>
                  <div className="text-sm text-slate-500 flex items-center gap-2">
                    <span>{formatFileSize(job.file.size)}</span>
                    <span>•</span>
                    <span>{job.message}</span>
                  </div>

                  {/* Progress Bar */}
                  {['uploading', 'processing'].includes(job.status) && (
                    <div className="mt-2 h-1.5 bg-slate-100 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-blue-500 transition-all duration-300"
                        style={{ width: `${job.progress}%` }}
                      />
                    </div>
                  )}
                </div>

                {/* Actions */}
                <div className="flex items-center gap-2 shrink-0">
                  {job.status === 'idle' && (
                    <button
                      onClick={() => processJob(job.id)}
                      className="p-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition"
                      title="Convert"
                    >
                      <Zap size={18} />
                    </button>
                  )}

                  {job.status === 'completed' && job.downloadUrl && (
                    <button
                      onClick={() => downloadFile(job.downloadUrl!, job.file.name)}
                      className="p-2 bg-green-500 text-white rounded-lg hover:bg-green-600 transition"
                      title="Download DOCX"
                    >
                      <Download size={18} />
                    </button>
                  )}

                  <button
                    onClick={() => removeJob(job.id)}
                    className="p-2 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition"
                    title="Remove"
                  >
                    <X size={18} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Convert All Button */}
        {jobs.some(j => j.status === 'idle') && (
          <div className="mt-6 text-center">
            <button
              onClick={processAll}
              className="
                inline-flex items-center gap-2 px-8 py-3
                bg-gradient-to-r from-blue-500 to-indigo-600
                text-white font-semibold rounded-full
                shadow-lg shadow-blue-500/25
                hover:shadow-xl hover:shadow-blue-500/30
                hover:scale-105 active:scale-95 transition-all
              "
            >
              <Zap size={20} fill="currentColor" />
              Convert All Files
            </button>
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="fixed bottom-0 left-0 right-0 bg-white border-t border-slate-200 py-3">
        <div className="max-w-5xl mx-auto px-6 text-center text-sm text-slate-500">
          Powered by Mistral AI • Supports scanned documents with OCR
        </div>
      </footer>
    </div>
  );
}

export default App;
