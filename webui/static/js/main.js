/**
 * 心念 WebUI 主脚本文件
 * 提供通用的 JavaScript 功能和工具函数
 */

// 全局配置
const CONFIG = {
    API_BASE_URL: '/api',
    REFRESH_INTERVAL: 30000,
    TOAST_DURATION: 4000,
    LOADING_MIN_TIME: 300
};

// ========== 工具函数 ==========
const Utils = {
    formatDateTime(dateString) {
        if (!dateString) return 'N/A';
        try {
            const date = new Date(dateString);
            return date.toLocaleString('zh-CN', {
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit'
            });
        } catch (error) {
            return dateString;
        }
    },

    formatRelativeTime(dateString) {
        if (!dateString) return 'N/A';
        try {
            const date = new Date(dateString);
            const now = new Date();
            const diff = now - date;
            const seconds = Math.floor(diff / 1000);
            const minutes = Math.floor(seconds / 60);
            const hours = Math.floor(minutes / 60);
            const days = Math.floor(hours / 24);

            if (days > 0) return `${days}天前`;
            if (hours > 0) return `${hours}小时前`;
            if (minutes > 0) return `${minutes}分钟前`;
            return '刚刚';
        } catch (error) {
            return dateString;
        }
    },

    debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    },

    throttle(func, limit) {
        let inThrottle;
        return function () {
            const args = arguments;
            const context = this;
            if (!inThrottle) {
                func.apply(context, args);
                inThrottle = true;
                setTimeout(() => inThrottle = false, limit);
            }
        };
    },

    deepClone(obj) {
        return JSON.parse(JSON.stringify(obj));
    },

    generateId() {
        return Math.random().toString(36).substr(2, 9);
    }
};

// ========== Toast 通知系统 ==========
const Toast = {
    _container: null,

    _ensureContainer() {
        if (!this._container) {
            this._container = document.createElement('div');
            this._container.className = 'toast-container';
            this._container.id = 'toast-container';
            document.body.appendChild(this._container);
        }
        return this._container;
    },

    _getIcon(type) {
        const icons = {
            success: 'fas fa-check',
            error: 'fas fa-exclamation',
            warning: 'fas fa-exclamation',
            info: 'fas fa-info'
        };
        return icons[type] || icons.info;
    },

    show(type, message, duration = CONFIG.TOAST_DURATION) {
        const container = this._ensureContainer();
        const id = 'toast_' + Utils.generateId();

        const toastEl = document.createElement('div');
        toastEl.className = `toast-item ${type}`;
        toastEl.id = id;
        toastEl.innerHTML = `
            <div class="toast-icon"><i class="${this._getIcon(type)}"></i></div>
            <div class="toast-text">${message}</div>
            <button class="toast-close" onclick="Toast.dismiss('${id}')"><i class="fas fa-times"></i></button>
        `;

        container.appendChild(toastEl);

        if (duration > 0) {
            setTimeout(() => this.dismiss(id), duration);
        }

        return id;
    },

    dismiss(id) {
        const el = document.getElementById(id);
        if (!el) return;
        el.classList.add('removing');
        setTimeout(() => el.remove(), 250);
    },

    success(message, duration) {
        return this.show('success', message, duration);
    },

    error(message, duration) {
        return this.show('error', message, duration);
    },

    warning(message, duration) {
        return this.show('warning', message, duration);
    },

    info(message, duration) {
        return this.show('info', message, duration);
    }
};

// ========== API 请求封装 ==========
const API = {
    async request(url, options = {}) {
        const defaultOptions = {
            headers: {
                'Content-Type': 'application/json',
            },
        };

        const config = { ...defaultOptions, ...options };

        try {
            const response = await fetch(url, config);
            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || `HTTP ${response.status}`);
            }

            return data;
        } catch (error) {
            console.error('API请求失败:', error);
            throw error;
        }
    },

    async get(endpoint, params = {}) {
        const url = new URL(CONFIG.API_BASE_URL + endpoint, window.location.origin);
        Object.keys(params).forEach(key => {
            if (params[key] !== null && params[key] !== undefined) {
                url.searchParams.append(key, params[key]);
            }
        });
        return this.request(url.toString());
    },

    async post(endpoint, data = {}) {
        return this.request(CONFIG.API_BASE_URL + endpoint, {
            method: 'POST',
            body: JSON.stringify(data),
        });
    },

    async put(endpoint, data = {}) {
        return this.request(CONFIG.API_BASE_URL + endpoint, {
            method: 'PUT',
            body: JSON.stringify(data),
        });
    },

    async delete(endpoint) {
        return this.request(CONFIG.API_BASE_URL + endpoint, {
            method: 'DELETE',
        });
    }
};

// ========== UI 组件和交互 ==========
const UI = {
    showLoading() {
        const overlay = document.getElementById('loading-overlay');
        if (overlay) {
            overlay.style.display = 'flex';
        }
    },

    hideLoading() {
        const overlay = document.getElementById('loading-overlay');
        if (overlay) {
            setTimeout(() => {
                overlay.style.display = 'none';
            }, CONFIG.LOADING_MIN_TIME);
        }
    },

    showMessage(type, message, duration = CONFIG.TOAST_DURATION) {
        Toast.show(type, message, duration);
    },

    getIconForType(type) {
        const icons = {
            success: 'check-circle',
            error: 'exclamation-triangle',
            warning: 'exclamation-circle',
            info: 'info-circle'
        };
        return icons[type] || 'info-circle';
    },

    async confirm(message, title = '确认操作') {
        return new Promise((resolve) => {
            const modalId = 'confirmModal_' + Utils.generateId();
            const modalHtml = `
                <div class="modal fade" id="${modalId}" tabindex="-1">
                    <div class="modal-dialog modal-dialog-centered">
                        <div class="modal-content">
                            <div class="modal-header">
                                <h5 class="modal-title">${title}</h5>
                                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                            </div>
                            <div class="modal-body">
                                <p class="mb-0">${message}</p>
                            </div>
                            <div class="modal-footer">
                                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
                                <button type="button" class="btn btn-primary" id="${modalId}_confirm">确认</button>
                            </div>
                        </div>
                    </div>
                </div>
            `;

            document.body.insertAdjacentHTML('beforeend', modalHtml);
            const modalElement = document.getElementById(modalId);
            const modal = new bootstrap.Modal(modalElement);

            document.getElementById(`${modalId}_confirm`).addEventListener('click', () => {
                modal.hide();
                resolve(true);
            });

            modalElement.addEventListener('hidden.bs.modal', () => {
                modalElement.remove();
                resolve(false);
            });

            modal.show();
        });
    },

    initTooltips() {
        const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
        tooltipTriggerList.map(function (tooltipTriggerEl) {
            return new bootstrap.Tooltip(tooltipTriggerEl);
        });
    },

    initPopovers() {
        const popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
        popoverTriggerList.map(function (popoverTriggerEl) {
            return new bootstrap.Popover(popoverTriggerEl);
        });
    }
};

// ========== 数据管理 ==========
const DataManager = {
    storage: {
        set(key, value) {
            try {
                localStorage.setItem('webui_' + key, JSON.stringify(value));
            } catch (error) {
                console.error('存储数据失败:', error);
            }
        },

        get(key, defaultValue = null) {
            try {
                const item = localStorage.getItem('webui_' + key);
                return item ? JSON.parse(item) : defaultValue;
            } catch (error) {
                console.error('读取数据失败:', error);
                return defaultValue;
            }
        },

        remove(key) {
            try {
                localStorage.removeItem('webui_' + key);
            } catch (error) {
                console.error('删除数据失败:', error);
            }
        },

        clear() {
            try {
                Object.keys(localStorage).forEach(key => {
                    if (key.startsWith('webui_')) {
                        localStorage.removeItem(key);
                    }
                });
            } catch (error) {
                console.error('清空数据失败:', error);
            }
        }
    },

    cache: new Map(),

    setCache(key, value, ttl = 300000) {
        this.cache.set(key, {
            value,
            expires: Date.now() + ttl
        });
    },

    getCache(key) {
        const item = this.cache.get(key);
        if (!item) return null;

        if (Date.now() > item.expires) {
            this.cache.delete(key);
            return null;
        }

        return item.value;
    },

    clearExpiredCache() {
        const now = Date.now();
        for (const [key, item] of this.cache.entries()) {
            if (now > item.expires) {
                this.cache.delete(key);
            }
        }
    }
};

// ========== 全局兼容函数 ==========
function showLoading() {
    UI.showLoading();
}

function hideLoading() {
    UI.hideLoading();
}

function showMessage(type, message) {
    UI.showMessage(type, message);
}

// ========== 主题管理 ==========
const ThemeManager = {
    _storageKey: 'webui_theme',

    init() {
        // 优先使用 localStorage，其次系统偏好
        const saved = localStorage.getItem(this._storageKey);
        if (saved) {
            this.apply(saved);
        } else if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
            this.apply('dark');
        } else {
            this.apply('light');
        }

        // 监听系统主题变化
        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
            if (!localStorage.getItem(this._storageKey)) {
                this.apply(e.matches ? 'dark' : 'light');
            }
        });
    },

    apply(theme) {
        document.documentElement.setAttribute('data-theme', theme);
        this._updateToggleButton(theme);
    },

    toggle() {
        const current = document.documentElement.getAttribute('data-theme') || 'light';
        const next = current === 'dark' ? 'light' : 'dark';
        localStorage.setItem(this._storageKey, next);
        this.apply(next);
    },

    _updateToggleButton(theme) {
        const btn = document.getElementById('themeToggle');
        if (!btn) return;
        const icon = btn.querySelector('i');
        const text = btn.querySelector('span');
        if (theme === 'dark') {
            icon.className = 'fas fa-sun';
            text.textContent = '浅色模式';
        } else {
            icon.className = 'fas fa-moon';
            text.textContent = '深色模式';
        }
    }
};

// ========== 数字滚动动画 ==========
function animateCountUp() {
    const elements = document.querySelectorAll('.count-up');
    elements.forEach(el => {
        const target = parseInt(el.dataset.target) || 0;
        if (target === 0) {
            el.textContent = '0';
            return;
        }
        const duration = 800;
        const startTime = performance.now();

        function update(currentTime) {
            const elapsed = currentTime - startTime;
            const progress = Math.min(elapsed / duration, 1);
            // easeOutCubic
            const eased = 1 - Math.pow(1 - progress, 3);
            const current = Math.round(eased * target);
            el.textContent = current;
            if (progress < 1) {
                requestAnimationFrame(update);
            } else {
                el.textContent = target;
            }
        }
        requestAnimationFrame(update);
    });
}

// ========== 页面初始化 ==========
document.addEventListener('DOMContentLoaded', function () {
    // 初始化主题
    ThemeManager.init();

    // 初始化数字动画
    animateCountUp();

    UI.initTooltips();
    UI.initPopovers();

    // 定期清理过期缓存
    setInterval(() => {
        DataManager.clearExpiredCache();
    }, 60000);

    // 全局错误处理
    window.addEventListener('error', function (event) {
        console.error('全局错误:', event.error);
    });

    window.addEventListener('unhandledrejection', function (event) {
        console.error('未处理的Promise拒绝:', event.reason);
    });

    // 页面加载完成的淡入效果
    document.body.classList.add('fade-in');

    console.log('心念 WebUI 已初始化');
});

// 导出到全局作用域
window.Utils = Utils;
window.API = API;
window.UI = UI;
window.Toast = Toast;
window.DataManager = DataManager;
window.ThemeManager = ThemeManager;