import { useCallback, useState, useRef } from 'react';
import './FileDropzone.css';

interface FileDropzoneProps {
  onFileSelect: (file: File) => void;
  accept?: string;
  maxSizeMB?: number;
  disabled?: boolean;
}

function FileDropzone({
  onFileSelect,
  accept = 'video/mp4,video/quicktime,video/x-matroska,video/webm,.mp4,.mov,.mkv,.webm,.avi',
  maxSizeMB = 5120,
  disabled = false,
}: FileDropzoneProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [error, setError] = useState<string>('');
  const inputRef = useRef<HTMLInputElement>(null);

  const validateFile = useCallback((file: File): string | null => {
    const allowedExtensions = ['.mp4', '.mov', '.avi', '.mkv', '.webm'];
    const ext = '.' + file.name.split('.').pop()?.toLowerCase();
    if (!allowedExtensions.includes(ext)) {
      return `Unsupported file type "${ext}". Allowed: MP4, MOV, AVI, MKV, WEBM.`;
    }
    if (file.size > maxSizeMB * 1024 * 1024) {
      return `File size (${formatSize(file.size)}) exceeds maximum limit of ${maxSizeMB} MB.`;
    }
    return null;
  }, [maxSizeMB]);

  const handleFile = useCallback((file: File) => {
    const validationError = validateFile(file);
    if (validationError) {
      setError(validationError);
      setSelectedFile(null);
      return;
    }
    setError('');
    setSelectedFile(file);
    onFileSelect(file);
  }, [validateFile, onFileSelect]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    if (!disabled) setIsDragging(true);
  }, [disabled]);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (disabled) return;
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  }, [disabled, handleFile]);

  const handleClick = () => {
    if (!disabled) inputRef.current?.click();
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
  };

  return (
    <div
      className={`dropzone-container ${isDragging ? 'dropzone-dragging' : ''} ${selectedFile ? 'dropzone-active-file' : ''} ${disabled ? 'dropzone-disabled' : ''}`}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      onClick={handleClick}
    >
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        onChange={handleInputChange}
        className="dropzone-hidden-input"
        disabled={disabled}
      />

      {selectedFile ? (
        <div className="dropzone-file-selected">
          <div className="file-icon-box">
            <span className="file-icon-symbol">▶</span>
          </div>
          <div className="file-meta-box">
            <span className="file-name font-mono">{selectedFile.name}</span>
            <span className="file-size font-mono">{formatSize(selectedFile.size)}</span>
          </div>
          {!disabled && (
            <button
              type="button"
              className="button-secondary btn-sm"
              onClick={(e) => {
                e.stopPropagation();
                setSelectedFile(null);
                setError('');
                if (inputRef.current) inputRef.current.value = '';
              }}
            >
              Replace
            </button>
          )}
        </div>
      ) : (
        <div className="dropzone-empty-state">
          <div className="dropzone-symbol-box">
            <span className="dropzone-crosshair">+</span>
          </div>
          <div className="dropzone-text-group">
            <span className="dropzone-prompt title-sm">
              Drop aerial drone footage here or click to browse
            </span>
            <span className="dropzone-specs font-mono">
              MP4 / MOV / AVI / MKV · MAX {(maxSizeMB / 1024).toFixed(0)} GB
            </span>
          </div>
        </div>
      )}

      {error && (
        <div className="dropzone-error-banner font-mono">
          <span>✕</span> {error}
        </div>
      )}
    </div>
  );
}

function formatSize(bytes: number): string {
  if (bytes === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return (bytes / Math.pow(1024, i)).toFixed(i > 1 ? 1 : 0) + ' ' + units[i];
}

export default FileDropzone;
