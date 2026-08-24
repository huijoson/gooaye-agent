// ========================================
// CONFIGURATION
// ========================================
const CONFIG = {
    // R2 CDN URLs for search indices - UPDATED 2025-08-20
    R2_BASE: 'https://pub-a4290b460c434360a6644d79072880dd.r2.dev/',
    
    // Progressive loading for fast startup
    USE_PROGRESSIVE: true,
    ENABLE_WORKER: false, // Disable worker for now - direct loading is faster
    PRELOAD_FULL: false, // Only load full index on demand - CRITICAL
    
    // Progressive indices - Primary URLs now point to R2 (no 404s)
    INDICES: {
        core: 'search_index_core.json',
        extended: 'search_index_extended.json',
        full: 'search_index_full.json'
    },
    
    // Size limits (MB) to prevent loading oversized indices
    SIZE_LIMITS: {
        core: 30,      // Max 30MB for core
        extended: 50,  // Max 50MB for extended
        full: 200      // Max 200MB for full (increased for growing index)
    },
    
    // Fallback to local if R2 fails
    FALLBACK_BASE: '/',
    
    // Episodes per page
    EPISODES_PER_PAGE: 10,
    
    // Search debounce delay (ms)
    SEARCH_DEBOUNCE: 300,
    
    // Preload timing
    PRELOAD_DELAY: 2000  // Start preloading extended index after 2s
};

// ========================================
// GLOBAL STATE
// ========================================
const state = {
    // Episode data
    allEpisodes: [],
    filteredEpisodes: [],
    currentPage: 1,
    currentSearchMode: 'content',  // Changed default to content
    
    // Date search
    dateSearchIndex: null,
    selectedDateType: 'year',
    selectedDateValue: '',
    
    // Progressive search indices
    indices: {
        core: null,
        extended: null,
        full: null
    },
    
    // Loading states
    loading: {
        core: false,
        extended: false,
        full: false
    },
    
    // Search state
    searchCache: new Map(),
    searchDebounceTimer: null,
    episodeContentCache: new Map(),
    searchStartTime: 0,
    
    // Web Worker for search
    searchWorker: null,
    searchCallbacks: new Map(),
    searchId: 0,
    currentIndexLevel: 'core',
    
    // Performance tracking
    indexLoadTimes: {}
};

// ========================================
// DOM ELEMENTS
// ========================================
const dom = {
    episodesContainer: null,
    paginationContainer: null,
    searchInput: null,
    searchBtn: null,
    clearBtn: null,
    episodeCount: null,
    sortSelect: null,
    contentSearchInput: null,
    contentSearchBtn: null,
    contentClearBtn: null,
    dateTypeSelect: null,
    dateValueSelect: null,
    dateSearchBtn: null,
    dateClearBtn: null
};

// ========================================
// INITIALIZATION
// ========================================
document.addEventListener('DOMContentLoaded', async () => {
    console.log('🚀 Initializing 股癌 Podcast with Progressive Search...');
    
    // Cache DOM elements
    initializeDOMElements();

    // Note: legacy 3-tier R2 search (initializeSearchWorker / loadCoreIndex
    // / loadExtendedIndex / loadFullIndex) was retired 2026-04-25 along
    // with the gooaye-search R2 bucket. Search now ships from the
    // single-pack TranscriptsPack path (bootTranscriptsPack below).

    // Load episodes
    await loadEpisodes();
    
    // Load date search index
    await loadDateSearchIndex();
    
    // Setup event handlers
    setupEventListeners();
    
    // Single-pack search system: download once, IDB-cache forever, search
    // in a Web Worker. The legacy 3-tier R2 indices have been retired.
    bootTranscriptsPack();
    
    // Handle URL parameters
    handleUrlParams();
});

function initializeDOMElements() {
    dom.episodesContainer = document.getElementById('episodes-container');
    dom.paginationContainer = document.getElementById('pagination');
    dom.searchInput = document.getElementById('search-input');
    dom.searchBtn = document.getElementById('search-btn');
    dom.clearBtn = document.getElementById('clear-btn');
    dom.episodeCount = document.getElementById('episode-count');
    dom.sortSelect = document.getElementById('sort-select');
    dom.contentSearchInput = document.getElementById('content-search-input');
    dom.contentSearchBtn = document.getElementById('content-search-btn');
    dom.contentClearBtn = document.getElementById('content-clear-btn');
    dom.yearSelect = document.getElementById('year-select');
    dom.monthSelect = document.getElementById('month-select');
    dom.dateSearchBtn = document.getElementById('date-search-btn');
    dom.dateClearBtn = document.getElementById('date-clear-btn');
}

// ========================================
// EPISODE LOADING
// ========================================
async function loadEpisodes() {
    try {
        dom.episodesContainer.innerHTML = '<div class="loading">Loading episodes...</div>';
        
        const response = await fetch('episodes.json', {
            mode: 'cors',
            credentials: 'omit',
            headers: {
                'Accept': 'application/json'
            }
        });
        state.allEpisodes = await response.json();
        state.filteredEpisodes = [...state.allEpisodes];
        
        // Apply default sort (newest first)
        handleSort();
        
        // Render latest episodes section
        renderLatestEpisodes();
        
        updateEpisodeCount();
        renderEpisodes();
        renderPagination();
        
        console.log(`✅ Loaded ${state.allEpisodes.length} episodes`);
    } catch (error) {
        console.error('Error loading episodes:', error);
        dom.episodesContainer.innerHTML = '<div class="empty-state">Error loading episodes. Please refresh the page.</div>';
    }
}

// ========================================
// DATE SEARCH FUNCTIONALITY
// ========================================
async function loadDateSearchIndex() {
    try {
        const response = await fetch('date_search_index.json', {
            mode: 'cors',
            credentials: 'omit',
            headers: {
                'Accept': 'application/json'
            }
        });
        state.dateSearchIndex = await response.json();
        console.log('✅ Loaded date search index');
        
        // Populate year dropdown
        if (dom.yearSelect) {
            populateYearOptions();
        }
    } catch (error) {
        console.error('Failed to load date search index:', error);
        // Create index on the fly if needed
        generateDateSearchIndex();
    }
}

function generateDateSearchIndex() {
    // Generate date index from episodes if the file doesn't exist
    const yearIndex = {};
    const monthIndex = {};
    const monthDisplay = {};
    
    state.allEpisodes.forEach(episode => {
        if (episode.year) {
            const year = episode.year.toString();
            if (!yearIndex[year]) yearIndex[year] = [];
            yearIndex[year].push(episode.number);
            
            const monthKey = `${episode.year}-${String(episode.month).padStart(2, '0')}`;
            if (!monthIndex[monthKey]) {
                monthIndex[monthKey] = [];
                const monthNames = ['January', 'February', 'March', 'April', 'May', 'June',
                                  'July', 'August', 'September', 'October', 'November', 'December'];
                monthDisplay[monthKey] = `${monthNames[episode.month - 1]} ${episode.year}`;
            }
            monthIndex[monthKey].push(episode.number);
        }
    });
    
    state.dateSearchIndex = {
        year_index: yearIndex,
        month_index: monthIndex,
        month_display: monthDisplay
    };
    
    console.log('✅ Generated date search index from episodes');
}

function populateYearOptions() {
    if (!dom.yearSelect || !state.dateSearchIndex) return;

    dom.yearSelect.innerHTML = '';

    // Add placeholder
    const placeholder = document.createElement('option');
    placeholder.value = '';
    placeholder.textContent = 'Select year 選擇年份...';
    dom.yearSelect.appendChild(placeholder);

    // Add years
    const years = Object.keys(state.dateSearchIndex.year_index).sort().reverse();
    years.forEach(year => {
        const option = document.createElement('option');
        option.value = year;
        const count = state.dateSearchIndex.year_index[year].length;
        option.textContent = `${year} (${count} episodes)`;
        dom.yearSelect.appendChild(option);
    });
}

function populateMonthOptions(selectedYear) {
    if (!dom.monthSelect || !state.dateSearchIndex) return;

    dom.monthSelect.innerHTML = '';

    if (!selectedYear) {
        // No year selected - disable and show placeholder
        dom.monthSelect.disabled = true;
        const placeholder = document.createElement('option');
        placeholder.value = '';
        placeholder.textContent = 'First select a year 請先選擇年份...';
        dom.monthSelect.appendChild(placeholder);
        return;
    }

    // Enable month select
    dom.monthSelect.disabled = false;

    // Add "All months" option
    const allOption = document.createElement('option');
    allOption.value = selectedYear;
    const yearCount = state.dateSearchIndex.year_index[selectedYear]?.length || 0;
    allOption.textContent = `All months 全年 (${yearCount} episodes)`;
    dom.monthSelect.appendChild(allOption);

    // Add specific months for the selected year
    const months = Object.keys(state.dateSearchIndex.month_index)
        .filter(month => month.startsWith(selectedYear + '-'))
        .sort()
        .reverse();

    months.forEach(month => {
        const option = document.createElement('option');
        option.value = month;
        const display = state.dateSearchIndex.month_display[month];
        const count = state.dateSearchIndex.month_index[month].length;
        option.textContent = `${display} (${count} episodes)`;
        dom.monthSelect.appendChild(option);
    });
}

function performDateSearch() {
    const selectedYear = dom.yearSelect?.value;
    const selectedMonth = dom.monthSelect?.value;

    if (!selectedYear || !state.dateSearchIndex) {
        handleClear();
        return;
    }

    let episodeNumbers = [];
    let displayText = '';

    // If month is selected and it's not just the year value
    if (selectedMonth && selectedMonth !== selectedYear) {
        // Search by specific month
        episodeNumbers = state.dateSearchIndex.month_index[selectedMonth] || [];
        displayText = state.dateSearchIndex.month_display[selectedMonth];
    } else {
        // Search by year (all months)
        episodeNumbers = state.dateSearchIndex.year_index[selectedYear] || [];
        displayText = selectedYear;
    }

    // Filter episodes
    state.filteredEpisodes = state.allEpisodes.filter(ep =>
        episodeNumbers.includes(ep.number)
    );

    // Sort by episode number (newest first)
    state.filteredEpisodes.sort((a, b) => b.number - a.number);

    // Update UI
    state.currentPage = 1;
    updateEpisodeCount(`Showing ${state.filteredEpisodes.length} episodes from ${displayText}`);
    renderEpisodes();
    renderPagination();
}

// ========================================
// WEB WORKER SEARCH MANAGEMENT
// ========================================
function initializeSearchWorker() {
    console.log('🚀 Search Config:', {
        ENABLE_WORKER: CONFIG.ENABLE_WORKER,
        PRELOAD_FULL: CONFIG.PRELOAD_FULL,
        USE_PROGRESSIVE: CONFIG.USE_PROGRESSIVE
    });
    
    // Check if worker is enabled in config
    if (!CONFIG.ENABLE_WORKER) {
        console.log('🔧 Search worker disabled - using direct index loading (faster)');
        loadCoreIndex();
        return;
    }
    
    try {
        state.searchWorker = new Worker('/search.worker.js');
        
        state.searchWorker.addEventListener('message', (e) => {
            handleWorkerMessage(e.data);
        });
        
        state.searchWorker.addEventListener('error', (error) => {
            console.error('Worker error:', error);
            // Fallback to non-worker search
            state.searchWorker = null;
            loadCoreIndex();
        });
        
        // Initialize worker
        state.searchWorker.postMessage({ type: 'init' });
        
    } catch (error) {
        console.warn('Web Worker not supported, using fallback search');
        loadCoreIndex();
    }
}

function handleWorkerMessage(data) {
    switch (data.type) {
        case 'ready':
        case 'worker-ready':
            console.log('Search worker ready');
            updateSearchStatus('Search ready (Fast mode)');
            enableContentSearch();
            // Preload extended index after a delay
            setTimeout(() => {
                if (state.searchWorker) {
                    state.searchWorker.postMessage({ 
                        type: 'load-index', 
                        indexLevel: 'extended' 
                    });
                }
            }, CONFIG.PRELOAD_DELAY);
            break;
            
        case 'index-loaded':
            console.log(`Loaded ${data.level} index with ${data.episodeCount} episodes`);
            state.currentIndexLevel = data.level;
            updateIndexStatus(data.level);
            break;
            
        case 'search-results':
            handleWorkerSearchResults(data);
            break;
            
        case 'error':
            console.error('Worker error:', data.message);
            updateSearchStatus('Search error. Please try again.');
            break;
    }
}

function handleWorkerSearchResults(data) {
    const callback = state.searchCallbacks.get(data.searchId);
    if (callback) {
        callback(data.results);
        state.searchCallbacks.delete(data.searchId);
    }
    
    // Display results
    displayWorkerSearchResults(data.results, data.query, data.indexLevel);
}

function displayWorkerSearchResults(results, query, indexLevel) {
    const searchTime = performance.now() - state.searchStartTime;
    
    if (results.length === 0) {
        dom.episodesContainer.innerHTML = `
            <div class="empty-state">
                No episodes found for "${query}"
                ${indexLevel !== 'full' ? '<br><small>Try loading more detailed search</small>' : ''}
            </div>
        `;
        state.filteredEpisodes = [];
        updateEpisodeCount();
        dom.paginationContainer.innerHTML = '';
        
        // Try to upgrade to next level if no results
        if (indexLevel === 'core' && state.searchWorker) {
            state.searchWorker.postMessage({ 
                type: 'load-index', 
                indexLevel: 'extended' 
            });
        } else if (indexLevel === 'extended' && state.searchWorker) {
            state.searchWorker.postMessage({ 
                type: 'load-index', 
                indexLevel: 'full' 
            });
        }
        return;
    }
    
    // Map results to episodes
    state.filteredEpisodes = results.map(result => {
        const episode = state.allEpisodes.find(ep => ep.number === result.id);
        if (episode) {
            return {
                ...episode,
                searchScore: result.score,
                searchContext: {
                    summary: result.summary,
                    highlights: result.highlights,
                    matchedWords: [query],
                    score: result.score
                }
            };
        }
        return null;
    }).filter(Boolean);
    
    // Update UI
    state.currentPage = 1;
    updateEpisodeCount(`Found ${results.length} episodes in ${searchTime.toFixed(0)}ms (${indexLevel} index)`);
    renderEpisodes();
    renderPagination();
}

function updateIndexStatus(level) {
    const searchNote = document.querySelector('.search-note');
    if (searchNote) {
        const levelText = {
            'core': 'Basic search ready',
            'extended': 'Extended search ready',
            'full': 'Full search ready'
        }[level] || 'Search ready';
        
        searchNote.textContent = levelText;
        searchNote.style.color = 'var(--color-success, #00aa00)';
    }
}

// ========================================
// PROGRESSIVE INDEX LOADING
// ========================================
async function loadCoreIndex() {
    if (state.indices.core || state.loading.core) return;
    
    state.loading.core = true;
    const startTime = performance.now();
    
    // Update UI
    const contentSearchTab = document.querySelector('[data-mode="content"]');
    const btnText = dom.contentSearchBtn?.querySelector('.btn-text');
    const loadingIndicator = dom.contentSearchBtn?.querySelector('.loading-indicator');
    const searchNote = document.querySelector('.search-note');
    
    // Show loading state
    if (contentSearchTab) {
        contentSearchTab.textContent = 'Search by Word 搜單詞 (Loading...)';
        contentSearchTab.disabled = true;
    }
    if (dom.contentSearchInput) {
        dom.contentSearchInput.placeholder = 'Loading search index...';
        dom.contentSearchInput.disabled = true;
    }
    if (btnText && loadingIndicator) {
        btnText.style.display = 'none';
        loadingIndicator.style.display = 'inline';
    }
    
    try {
        console.log('📦 Loading core search index...');
        
        // Primary URL now points to R2 (no 404s) - Add cache buster
        const cacheBuster = Date.now();
        let url = CONFIG.R2_BASE + CONFIG.INDICES.core + '?t=' + cacheBuster;
        
        console.log('📦 Loading lightweight core index from R2... (4.9MB, ~1s)');
        let response = await fetch(url, {
            mode: 'cors',
            credentials: 'omit',
            headers: {
                'Accept': 'application/json'
            }
        });
        
        if (!response.ok) {
            throw new Error(`Core index failed: ${response.status}`);
        }
        
        // Log size and check limits
        const contentLength = response.headers.get('content-length');
        if (contentLength) {
            const sizeMB = parseInt(contentLength) / (1024 * 1024);
            console.log(`   Core index size: ${sizeMB.toFixed(1)}MB`);
            
            // Size guard
            if (sizeMB > CONFIG.SIZE_LIMITS.core) {
                throw new Error(`Core index too large: ${sizeMB.toFixed(1)}MB > ${CONFIG.SIZE_LIMITS.core}MB`);
            }
        }
        
        // Enable search UI immediately after download (before parsing)
        console.log('📥 Download complete! Enabling search UI...');
        
        // Enable search UI first
        const contentSearchTab = document.querySelector('[data-mode=\"content\"]');
        const contentSearchInput = document.getElementById('content-search-input');
        const contentSearchBtn = document.getElementById('content-search-btn');
        
        if (contentSearchTab) {
            contentSearchTab.textContent = 'Search by Word 搜單詞';
            contentSearchTab.disabled = false;
            contentSearchTab.style.opacity = '1';
        }
        if (contentSearchInput) {
            contentSearchInput.placeholder = 'Search episode content...';
            contentSearchInput.disabled = false;
        }
        if (contentSearchBtn) {
            const btnText = contentSearchBtn.querySelector('.btn-text');
            const loadingIndicator = contentSearchBtn.querySelector('.loading-indicator');
            if (btnText && loadingIndicator) {
                btnText.textContent = 'Search';
                btnText.style.display = 'inline';
                loadingIndicator.style.display = 'none';
            }
            contentSearchBtn.disabled = false;
        }
        
        // CRITICAL FIX: Store the parsed core index data
        const coreData = await response.json();
        state.indices.core = coreData;
        const isMobile = /iPhone|iPad|iPod|Android/i.test(navigator.userAgent);
        console.log('✅ Core index stored to state with', Object.keys(coreData.word_index || {}).length, 'words', isMobile ? '(Mobile)' : '(Desktop)');
        
        // Update search note
        if (searchNote) {
            searchNote.textContent = 'Search ready! Loading more words in background...';
            searchNote.style.color = 'var(--color-success, green)';
        }
        
        // Start loading extended index for better results
        setTimeout(() => {
            loadExtendedIndex();
        }, 500);
        
    } catch (error) {
        console.error('Failed to load core index:', error);
        
        // Update UI to show error state
        if (contentSearchTab) {
            contentSearchTab.textContent = 'Search by Word 搜單詞 (Unavailable)';
            contentSearchTab.style.opacity = '0.5';
            contentSearchTab.disabled = true;
        }
        if (dom.contentSearchInput) {
            dom.contentSearchInput.placeholder = 'Content search unavailable - please refresh page';
            dom.contentSearchInput.disabled = true;
        }
        if (btnText && loadingIndicator) {
            btnText.textContent = 'Search Unavailable';
            btnText.style.display = 'inline';
            loadingIndicator.style.display = 'none';
        }
        if (searchNote) {
            searchNote.textContent = 'Failed to load search index. Please refresh the page.';
            searchNote.style.color = 'var(--color-error, red)';
        }
    } finally {
        state.loading.core = false;
    }
}

async function loadExtendedIndex() {
    if (state.indices.extended || state.loading.extended) return;
    
    state.loading.extended = true;
    const startTime = performance.now();
    
    try {
        console.log('📦 Loading extended index from R2... (background)');
        
        const url = CONFIG.R2_BASE + CONFIG.INDICES.extended + '?t=' + Date.now();
        const response = await fetch(url, {
            mode: 'cors',
            credentials: 'omit',
            headers: {
                'Accept': 'application/json'
            }
        });
        
        if (!response.ok) {
            throw new Error(`Extended index failed: ${response.status}`);
        }
        
        // Log size and check limits
        const contentLength = response.headers.get('content-length');
        if (contentLength) {
            const sizeMB = parseInt(contentLength) / (1024 * 1024);
            console.log(`   Extended index size: ${sizeMB.toFixed(1)}MB`);
            
            // Size guard
            if (sizeMB > CONFIG.SIZE_LIMITS.extended) {
                throw new Error(`Extended index too large: ${sizeMB.toFixed(1)}MB > ${CONFIG.SIZE_LIMITS.extended}MB`);
            }
        }
        
        state.indices.extended = await response.json();
        state.indexLoadTimes.extended = performance.now() - startTime;
        
        const isMobile = /iPhone|iPad|iPod|Android/i.test(navigator.userAgent);
        console.log(`✅ Extended index loaded in ${(state.indexLoadTimes.extended/1000).toFixed(1)}s`, isMobile ? '(Mobile)' : '(Desktop)');
        
        
        // Re-run current search if any to show more results
        if (state.currentSearchMode === 'content' && dom.contentSearchInput?.value) {
            performContentSearch(dom.contentSearchInput.value);
        }
        
    } catch (error) {
        console.error('Extended index failed:', error);
    } finally {
        state.loading.extended = false;
    }
}

async function loadFullIndex() {
    if (state.indices.full || state.loading.full) return;
    
    state.loading.full = true;
    const startTime = performance.now();
    
    try {
        console.log('📦 Loading full search index...');
        updateSearchStatus('Loading complete index for rare terms...');
        
        // Primary URL now points to R2 (no 404s) - Add cache buster  
        let url = CONFIG.R2_BASE + CONFIG.INDICES.full + '?t=' + Date.now();
        let response = await fetchWithTimeout(url, 60000);
        
        if (!response.ok) {
            // Fallback to local files
            console.log('Trying local fallback for full index...');
            url = CONFIG.FALLBACK_BASE + CONFIG.INDICES.full;
            response = await fetch(url, {
                mode: 'cors',
                credentials: 'omit',
                headers: {
                    'Accept': 'application/json'
                }
            });
        }
        
        // Check size before parsing
        const contentLength = response.headers.get('content-length');
        if (contentLength) {
            const sizeMB = parseInt(contentLength) / (1024 * 1024);
            console.log(`   Full index size: ${sizeMB.toFixed(1)}MB`);
            
            // Size guard - allow reasonable sizes on mobile  
            const isMobile = /iPhone|iPad|iPod|Android/i.test(navigator.userAgent);
            const maxSize = isMobile ? 80 : CONFIG.SIZE_LIMITS.full; // Allow up to 80MB on mobile (was 30MB)
            
            if (sizeMB > maxSize) {
                if (isMobile) {
                    console.warn(`⚠️  Full index too large for mobile (${sizeMB.toFixed(1)}MB > ${maxSize}MB). Trying progressive loading...`);
                    // Don't return - let it try to load, mobile devices can handle 65MB
                    console.log('📱 Mobile detected but attempting load anyway - modern phones can handle this');
                } else {
                    throw new Error(`Full index too large: ${sizeMB.toFixed(1)}MB > ${CONFIG.SIZE_LIMITS.full}MB`);
                }
            }
        }
        
        state.indices.full = await response.json();
        state.indexLoadTimes.full = performance.now() - startTime;
        
        const isMobile = /iPhone|iPad|iPod|Android/i.test(navigator.userAgent);
        console.log(`✅ Full index loaded in ${state.indexLoadTimes.full.toFixed(0)}ms`, isMobile ? '(Mobile)' : '(Desktop)');
        
        if (isMobile) {
            updateSearchStatus('Full search ready on mobile! All terms searchable.', 3000);
        } else {
            updateSearchStatus('Full index loaded - all terms searchable!', 2000);
        }
        
        // Re-run search with full index
        if (state.currentSearchMode === 'content' && dom.contentSearchInput?.value) {
            performContentSearch(dom.contentSearchInput.value);
        }
        
    } catch (error) {
        console.error('Failed to load full index:', error);
        updateSearchStatus('Failed to load complete index', 3000);
    } finally {
        state.loading.full = false;
    }
}

// ========================================
// PROGRESSIVE LOADING STRATEGY
// ========================================
function setupProgressiveLoading() {
    // Preload extended index immediately after core
    setTimeout(() => {
        if (!state.indices.extended && !state.loading.extended) {
            loadExtendedIndex();
        }
    }, 1000); // Load after 1 second
    
    // Only preload full index if enabled in config
    if (CONFIG.PRELOAD_FULL) {
        console.log('📦 Full index preload enabled - loading in 3 seconds...');
        setTimeout(() => {
            if (!state.indices.full && !state.loading.full) {
                console.log('📦 Preloading full index for comprehensive search...');
                loadFullIndex();
            }
        }, 3000); // Load after 3 seconds
    } else {
        console.log('⚡ Full index preload disabled - will load on demand only');
    }
    
    // Also preload on search button hover
    const contentSearchTab = document.querySelector('.search-tab[data-mode="content"]');
    if (contentSearchTab) {
        contentSearchTab.addEventListener('mouseenter', () => {
            if (!state.indices.extended && !state.loading.extended) {
                loadExtendedIndex();
            }
            // Also start loading full index on hover (if enabled)
            if (!state.indices.full && !state.loading.full && CONFIG.PRELOAD_FULL) {
                console.log('🖱️ Mouse hover detected - loading full index...');
                loadFullIndex();
            }
        }, { once: true });
    }
}

// ========================================
// SEARCH IMPLEMENTATION
// ========================================
function performContentSearch(query) {
    if (!query.trim()) {
        handleClear();
        return;
    }
    
    state.searchStartTime = performance.now();
    
    // Check cache first
    const cacheKey = `${query}_${getAvailableIndexType()}`;
    if (state.searchCache.has(cacheKey)) {
        const cached = state.searchCache.get(cacheKey);
        displaySearchResults(cached.results, cached.indexType);
        return;
    }
    
    // Clear previous timer
    clearTimeout(state.searchDebounceTimer);
    
    // Show searching state immediately
    dom.episodesContainer.innerHTML = '<div class="loading">Searching...</div>';
    
    // Debounce search
    state.searchDebounceTimer = setTimeout(() => {
        executeSearch(query);
    }, CONFIG.SEARCH_DEBOUNCE);
}

function segmentChineseQuery(query) {
    // Handle known phrases that should be split for better search results
    const knownPhrases = {
        '秋口幹你娘': ['秋口', '幹你娘'],
        '財富自由': ['財富', '自由'],
        '中裕新藥': ['中裕', '新藥'],
        '台積電': ['台積電'], // Keep as single term
        '股價': ['股價'], // Keep as single term
        // Add more problematic phrases as needed
    };
    
    // Check if query matches any known phrases
    if (knownPhrases[query]) {
        return knownPhrases[query];
    }
    
    // For other Chinese text, try simple segmentation
    // This is a basic approach - could be improved with proper Chinese segmentation
    const result = [];
    let current = '';
    
    for (let i = 0; i < query.length; i++) {
        const char = query[i];
        current += char;
        
        // Basic Chinese word boundary detection (simplified)
        if (current.length >= 2) {
            result.push(current);
            current = '';
        }
    }
    
    // Add remaining characters
    if (current) {
        result.push(current);
    }
    
    // If segmentation produces too many tiny pieces, return original
    if (result.length > 3 || result.some(seg => seg.length < 2)) {
        return [query];
    }
    
    return result.length > 1 ? result : [query];
}

async function searchExactPhrase(phrase) {
    // Cache for episode content to avoid multiple fetches
    if (!state.episodeContentCache) {
        state.episodeContentCache = new Map();
    }
    
    const results = [];
    const candidateEpisodes = [];
    
    // Get candidate episodes that might contain the phrase
    // Check if any component words exist in the index to narrow down candidates
    const segmented = segmentChineseQuery(phrase);
    if (segmented.length > 1 && state.indices.core) {
        const wordIndex = state.indices.core.word_index;
        const episodeSets = segmented.map(word => new Set(wordIndex[word] || []));
        
        if (episodeSets.length > 0) {
            // Get intersection of all word sets
            let intersection = episodeSets[0];
            for (let i = 1; i < episodeSets.length; i++) {
                intersection = new Set([...intersection].filter(x => episodeSets[i].has(x)));
            }
            candidateEpisodes.push(...intersection);
        }
    }
    
    // If no candidates from word intersection, check all episodes (expensive)
    if (candidateEpisodes.length === 0) {
        candidateEpisodes.push(...state.allEpisodes.map(ep => ep.number));
    }
    
    // Check each candidate episode for exact phrase
    for (const epNum of candidateEpisodes.slice(0, 50)) { // Limit to prevent too many requests
        try {
            const episode = state.allEpisodes.find(ep => ep.number === epNum);
            if (!episode) continue;
            
            let content = state.episodeContentCache.get(episode.filename);
            if (!content) {
                const response = await fetch(`episodes/${encodeURIComponent(episode.filename)}`, {
                    mode: 'cors',
                    credentials: 'omit'
                });
                
                if (response.ok) {
                    content = await response.text();
                    state.episodeContentCache.set(episode.filename, content);
                }
            }
            
            if (content && content.includes(phrase)) {
                // Count occurrences for scoring
                const matches = (content.match(new RegExp(phrase, 'g')) || []).length;
                results.push({ ...episode, searchScore: matches, exactMatch: true });
            }
        } catch (error) {
            console.warn(`Failed to check episode ${epNum} for phrase:`, error);
        }
    }
    
    // Sort by score (number of phrase occurrences) and episode number
    return results.sort((a, b) => {
        if (a.searchScore !== b.searchScore) return b.searchScore - a.searchScore;
        return b.number - a.number;
    });
}

// ─── New single-pack search system (preferred when ready) ────────────────
async function bootTranscriptsPack() {
    if (!window.TranscriptsPack) {
        // No pack module → leave the search UI disabled with a note.
        const searchNote = document.querySelector('.search-note');
        if (searchNote) {
            searchNote.textContent = 'Search unavailable (transcripts pack not found).';
        }
        return;
    }
    try {
        const result = await window.TranscriptsPack.boot();
        if (result && result.episodeCount) {
            console.log(
                `✅ Transcript pack ready (${result.episodeCount} eps, ` +
                `${result.cached ? 'from cache' : 'just downloaded'}, ` +
                `version ${result.version})`
            );
            enableContentSearch();
        }
    } catch (err) {
        console.warn('Transcript pack failed to boot:', err);
        const searchNote = document.querySelector('.search-note');
        if (searchNote) {
            searchNote.textContent = 'Search pack failed to load — try refresh.';
        }
    }
}

async function executeSearchPack(query) {
    state.searchStartTime = performance.now();
    let response;
    try {
        response = await window.TranscriptsPack.search(query, 200);
    } catch (err) {
        console.error('Pack search failed, falling back to legacy:', err);
        return null;
    }
    const hits = response.hits || [];

    // Map hits onto episode objects so renderEpisodes can render them.
    const epByNumber = new Map(state.allEpisodes.map(ep => [ep.number, ep]));
    const results = hits.map(hit => {
        const ep = epByNumber.get(hit.n);
        if (!ep) return null;
        return Object.assign({}, ep, {
            searchScore: hit.matchCount,
            searchContext: {
                matchedWords: [query],
                score: hit.matchCount,
                snippet: hit.snippet,
                field: hit.field,
                preview: hit.snippet ? null : `Matched ${hit.matchCount} time${hit.matchCount > 1 ? 's' : ''}`,
            },
        });
    }).filter(Boolean);

    displaySearchResults(results, 'pack', [query]);
    return results;
}

async function executeSearch(query) {
    // Single-pack worker is the only search path. If the pack hasn't booted
    // yet (first visit, still downloading), wait briefly for it; if it never
    // arrives, surface an error so the user knows to retry rather than
    // silently failing.
    if (!window.TranscriptsPack) {
        dom.episodesContainer.innerHTML =
            '<div class="empty-state">Search is unavailable. Please reload the page.</div>';
        return;
    }

    if (window.TranscriptsPack.state !== 'ready') {
        dom.episodesContainer.innerHTML =
            '<div class="loading">Loading search pack… first visit takes a few seconds.</div>';
        try {
            await window.TranscriptsPack.boot();
        } catch (err) {
            console.error('Pack boot failed:', err);
            dom.episodesContainer.innerHTML =
                `<div class="empty-state">Search pack failed to load: ${(err && err.message) || err}</div>`;
            return;
        }
    }

    await executeSearchPack(query);
}

function searchInIndex(index, queryTerms) {
    const matchingEpisodes = new Map();
    
    console.log('🔍 Searching for terms:', queryTerms);
    console.log('📊 Index has word_index keys:', Object.keys(index.word_index || {}).length);
    
    // Search for each term
    queryTerms.forEach(term => {
        const episodes = index.word_index[term] || [];
        console.log(`   "${term}": ${episodes.length} episodes found`, episodes.slice(0, 3));
        episodes.forEach(epNum => {
            matchingEpisodes.set(epNum, (matchingEpisodes.get(epNum) || 0) + 1);
        });
    });
    
    console.log('🎯 Total matching episodes:', matchingEpisodes.size);
    
    // Sort by relevance (number of matching terms) and episode number
    const sorted = Array.from(matchingEpisodes.entries())
        .sort((a, b) => {
            const scoreA = a[1];
            const scoreB = b[1];
            if (scoreA !== scoreB) return scoreB - scoreA;
            return b[0] - a[0]; // Newer episodes first for same score
        });
    
    // Get episode details
    const results = sorted.map(([epNum, score]) => {
        const episode = state.allEpisodes.find(ep => ep.number === epNum);
        if (episode) {
            return { ...episode, searchScore: score };
        }
        return null;
    }).filter(Boolean);
    
    return results;
}

function displaySearchResults(results, indexType, queryTerms = []) {
    const queryString = queryTerms.join(' ');

    if (results.length === 0) {
        // Single-pack search is single-shot — no more indices to wait on.
        // Show "no results" immediately rather than a perpetual spinner.
        dom.episodesContainer.innerHTML = `
            <div class="empty-state">
                找不到「${queryString}」相關的集數
            </div>
        `;
        state.filteredEpisodes = [];
        updateEpisodeCount(`謝孟恭沒有提到「${queryString}」`);
        dom.paginationContainer.innerHTML = '';
        return;
    }
    
    // Update filtered episodes with search results.
    // executeSearchPack already attaches a rich searchContext (with snippet
    // + offset). Preserve it so the click handler can build deep links.
    state.filteredEpisodes = results.map(result => ({
        ...result,
        searchContext: result.searchContext || {
            matchedWords: queryTerms,
            score: result.searchScore,
            preview: `Matched ${result.searchScore} term${result.searchScore > 1 ? 's' : ''}`
        }
    }));
    
    // Update UI
    state.currentPage = 1;
    updateEpisodeCount(`謝孟恭在 ${results.length} 集中提到「${queryString}」`);
    renderEpisodes();
    renderPagination();
}

// ========================================
// UI HELPERS
// ========================================
function showProgressiveSearchLoading(queryString, currentIndexType) {
    const loadingMessage = currentIndexType === 'core' 
        ? `Still loading results for "${queryString}"...`
        : `Searching full index for "${queryString}"...`;
    
    dom.episodesContainer.innerHTML = `
        <div class="progressive-search-loading">
            <div class="loading-spinner"></div>
            <span>${loadingMessage}</span>
        </div>
    `;
}
function enableContentSearch() {
    const contentSearchTab = document.querySelector('[data-mode="content"]');
    const btnText = dom.contentSearchBtn?.querySelector('.btn-text');
    const loadingIndicator = dom.contentSearchBtn?.querySelector('.loading-indicator');
    
    if (dom.contentSearchInput) {
        dom.contentSearchInput.disabled = false;
        dom.contentSearchInput.placeholder = 'Search episode content (e.g., 幹, LoveGG, 快樂寶貝, 秋口幹你娘)';
    }
    
    if (contentSearchTab) {
        // Keep the original text instead of overwriting it
        contentSearchTab.disabled = false;
        // Remove loading indicator if it was added
        if (contentSearchTab.textContent.includes('Loading')) {
            contentSearchTab.textContent = 'Search by Word 搜單詞';
        }
    }
    
    if (btnText && loadingIndicator) {
        btnText.style.display = 'inline';
        loadingIndicator.style.display = 'none';
    }
}

function updateSearchStatus(message, timeout = 0) {
    const searchNote = document.querySelector('.search-note');
    if (searchNote) {
        searchNote.textContent = message;
        searchNote.style.color = 'var(--color-info, #0066cc)';
        
        if (timeout > 0) {
            setTimeout(() => {
                searchNote.textContent = 'Search ready! More results will load in background.';
                searchNote.style.color = 'var(--color-muted)';
            }, timeout);
        }
    }
}

function getAvailableIndexType() {
    if (state.indices.full) return 'full';
    if (state.indices.extended) return 'extended';
    if (state.indices.core) return 'core';
    return 'none';
}

// ========================================
// EVENT HANDLERS
// ========================================
function setupEventListeners() {
    // Episode number search
    dom.searchBtn?.addEventListener('click', handleNumberSearch);
    dom.clearBtn?.addEventListener('click', handleClear);
    dom.searchInput?.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') handleNumberSearch();
    });
    
    // Content search
    dom.contentSearchBtn?.addEventListener('click', handleContentSearch);
    dom.contentClearBtn?.addEventListener('click', handleClear);
    dom.contentSearchInput?.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') handleContentSearch();
    });
    
    // Date search - year selection
    dom.yearSelect?.addEventListener('change', (e) => {
        const selectedYear = e.target.value;
        state.selectedYear = selectedYear;
        state.selectedMonth = ''; // Reset month selection
        populateMonthOptions(selectedYear);
    });

    // Date search - month selection
    dom.monthSelect?.addEventListener('change', (e) => {
        state.selectedMonth = e.target.value;
    });
    
    dom.dateSearchBtn?.addEventListener('click', performDateSearch);
    dom.dateClearBtn?.addEventListener('click', handleClear);
    
    // Sort
    dom.sortSelect?.addEventListener('change', handleSort);
    
    // Search mode tabs
    const searchTabs = document.querySelectorAll('.search-tab');
    const numberSearch = document.getElementById('number-search');
    const contentSearch = document.getElementById('content-search');
    const dateSearch = document.getElementById('date-search');
    
    // Set initial state - content search is default
    if (contentSearch && numberSearch) {
        contentSearch.style.display = 'flex';
        numberSearch.style.display = 'none';
        dateSearch.style.display = 'none';
    }
    
    searchTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            searchTabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            
            state.currentSearchMode = tab.dataset.mode;
            
            // Show/hide search containers
            if (state.currentSearchMode === 'number') {
                numberSearch.style.display = 'flex';
                contentSearch.style.display = 'none';
                dateSearch.style.display = 'none';
            } else if (state.currentSearchMode === 'date') {
                numberSearch.style.display = 'none';
                contentSearch.style.display = 'none';
                dateSearch.style.display = 'flex';
            } else {
                numberSearch.style.display = 'none';
                contentSearch.style.display = 'flex';
                dateSearch.style.display = 'none';
                
                // Load extended index when content search is selected
                if (!state.indices.extended && !state.loading.extended) {
                    loadExtendedIndex();
                }
            }
            
            // Clear any active searches when switching modes
            handleClear();
        });
    });
}

function handleNumberSearch() {
    const searchTerm = dom.searchInput.value.trim().toLowerCase();
    
    if (searchTerm === '') {
        handleClear();
        return;
    }
    
    // Extract number from search term
    const searchNumber = parseInt(searchTerm.replace(/[^\d]/g, ''));
    
    if (!isNaN(searchNumber)) {
        // Search by episode number
        state.filteredEpisodes = state.allEpisodes.filter(ep => ep.number === searchNumber);
    } else {
        // Search by title (fallback)
        state.filteredEpisodes = state.allEpisodes.filter(ep => 
            ep.title.toLowerCase().includes(searchTerm)
        );
    }
    
    state.currentPage = 1;
    updateEpisodeCount();
    renderEpisodes();
    renderPagination();
}

function handleContentSearch() {
    const searchTerm = dom.contentSearchInput.value.trim();

    if (!searchTerm) {
        handleClear();
        return;
    }

    // Single-pack TranscriptsPack is the only search path. performContentSearch
    // → executeSearch waits for the pack if it isn't ready yet, so no
    // pre-flight readiness check is needed here.
    performContentSearch(searchTerm);
}

function performWorkerSearch(query) {
    state.searchStartTime = performance.now();
    const searchId = ++state.searchId;
    
    // Show loading state
    dom.episodesContainer.innerHTML = '<div class="loading">Searching...</div>';
    
    // Send search request to worker
    state.searchWorker.postMessage({
        type: 'search',
        query: query,
        indexLevel: state.currentIndexLevel,
        searchId: searchId
    });
    
    // Set timeout for search
    setTimeout(() => {
        if (state.searchCallbacks.has(searchId)) {
            state.searchCallbacks.delete(searchId);
            updateSearchStatus('Search timeout. Please try again.');
        }
    }, 5000);
}

function handleClear() {
    dom.searchInput.value = '';
    dom.contentSearchInput.value = '';

    state.filteredEpisodes = [...state.allEpisodes];
    handleSort(); // Apply current sort
    state.currentPage = 1;
    updateEpisodeCount();
    renderEpisodes();
    renderPagination();
}

function handleSort() {
    const sortValue = dom.sortSelect.value;
    
    if (sortValue === 'newest') {
        state.filteredEpisodes.sort((a, b) => b.number - a.number);
    } else {
        state.filteredEpisodes.sort((a, b) => a.number - b.number);
    }
    
    state.currentPage = 1;
    renderEpisodes();
    renderPagination();
}

// ========================================
// RENDERING
// ========================================
function updateEpisodeCount(customMessage = null) {
    if (customMessage) {
        dom.episodeCount.textContent = customMessage;
        return;
    }
    
    const total = state.allEpisodes.length;
    const filtered = state.filteredEpisodes.length;
    
    if (filtered === total) {
        dom.episodeCount.textContent = `${total} episodes total`;
    } else {
        dom.episodeCount.textContent = `Showing ${filtered} of ${total} episodes`;
    }
}

function renderLatestEpisodes() {
    const latestContainer = document.getElementById('latest-episodes-list');
    if (!latestContainer) return;

    // Curated classic episodes for beginners with custom descriptions
    const classicEpisodesData = [
        { number: 339, note: '剪破衣服（經典梗）' },
        { number: 117, note: '秋口幹你娘（經典梗）' },
        { number: 102, note: '小朋友才做選擇（談配置）' },
        { number: 169, note: '損害控制（談停損）' },
        { number: 180, note: '入魔（談初探股票，勿入魔基本面、籌碼面與技術面，應選擇適合自己的工具箱組合）' },
        { number: 260, note: '談到槓桿ETF 適合的用法' },
        { number: 275, note: '期貨' },
        { number: 327, note: '快速致富風險' },
        { number: 20, note: '財你個鳥富自由 討論騙人的話術（臭一下財富自由概念）' },
        { number: 57, note: '跟風仔都該聊台積電 柳樹理論（台積電本益比、台灣央行）' },
        { number: 550, note: '癌大笑觀眾ID：puma台語叫破麻，但阿嬤阿茲海默（經典梗）' }
    ];

    // Find these episodes in our data and add custom note
    const allPopularEpisodes = classicEpisodesData
        .map(data => {
            const episode = state.allEpisodes.find(ep => ep.number === data.number);
            return episode ? { ...episode, customNote: data.note } : null;
        })
        .filter(Boolean);

    latestContainer.innerHTML = '';
    allPopularEpisodes.forEach(episode => {
        const episodeElement = createEpisodeElement(episode, true); // true = enhanced title
        latestContainer.appendChild(episodeElement);
    });
}

function renderEpisodes(scrollToTop = false) {
    if (state.filteredEpisodes.length === 0) {
        dom.episodesContainer.innerHTML = '<div class="empty-state">No episodes found. Try a different search.</div>';
        return;
    }
    
    const startIndex = (state.currentPage - 1) * CONFIG.EPISODES_PER_PAGE;
    const endIndex = startIndex + CONFIG.EPISODES_PER_PAGE;
    const pageEpisodes = state.filteredEpisodes.slice(startIndex, endIndex);
    
    dom.episodesContainer.innerHTML = '';
    
    pageEpisodes.forEach(episode => {
        const episodeElement = createEpisodeElement(episode, true); // Use enhanced titles for all episodes
        dom.episodesContainer.appendChild(episodeElement);
    });
    
    // Scroll to search controls when changing pages
    if (scrollToTop) {
        const searchControls = document.querySelector('.controls');
        if (searchControls) {
            searchControls.scrollIntoView({ behavior: 'smooth', block: 'start' });
        } else {
            // Fallback to top if controls not found
            window.scrollTo({ top: 0, behavior: 'smooth' });
        }
    }
}

function createEpisodeElement(episode, enhancedTitle = false) {
    // Render as a real anchor so the browser's native navigation works:
    // right-click → "open in new tab", middle-click, and Cmd/Ctrl+click all
    // behave as expected. (Previously this was an <article> with a JS click
    // handler, which only supported same-tab left clicks.)
    const article = document.createElement('a');
    article.className = 'episode';

    let displayTitle = episode.display_title || episode.title;
    let episodePrefix = enhancedTitle ? `股癌逐字稿 EP${episode.number}：` : `EP${episode.number}`;
    
    // Format date if available
    let dateDisplay = '';
    if (episode.date) {
        // Parse date components directly to avoid timezone issues
        // episode.date is in format "YYYY-MM-DD"
        const [year, month, day] = episode.date.split('-').map(Number);
        const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                          'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
        const dayStr = day.toString().padStart(2, '0');
        dateDisplay = `${dayStr} ${monthNames[month - 1]} ${year}`;
    }
    
    // Show search context if available
    let contextHTML = '';
    if (episode.searchContext) {
        const ctx = episode.searchContext;
        if (ctx.snippet && (ctx.snippet.before !== undefined || ctx.snippet.match !== undefined)) {
            // New single-pack search: show actual transcript snippet with the hit highlighted.
            const escapeHtml = s => (s || '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
            const fieldLabel = ctx.field === 'title' ? '標題' : ctx.field === 'description' ? '描述' : '逐字稿';
            contextHTML = `<div class="search-context search-snippet">
                <span class="search-match-info">${fieldLabel}命中 · ${ctx.score} 處</span>
                <div class="snippet-text">${escapeHtml(ctx.snippet.before)}<mark>${escapeHtml(ctx.snippet.match)}</mark>${escapeHtml(ctx.snippet.after)}</div>
            </div>`;
        } else {
            contextHTML = `<div class="search-context">
                <span class="search-match-info">Matched: ${ctx.matchedWords.join(', ')} (${ctx.score} matches)</span>
            </div>`;
        }
    }
    
    // Use customNote for classic episodes, otherwise prefer summary (LLM-generated)
    // and fall back to description (first line of transcript) for episodes without one
    const descriptionText = episode.customNote || episode.summary || episode.description || '';

    article.innerHTML = `
        <div class="episode-header">
            <span class="episode-number">${episodePrefix}</span>
            ${dateDisplay ? `<span class="episode-date">${dateDisplay}</span>` : ''}
            <div class="episode-title">${displayTitle || ''}</div>
        </div>
        ${descriptionText ? `<div class="episode-description">${descriptionText}</div>` : ''}
        ${contextHTML}
    `;
    
    // Build the episode-viewer URL as the anchor's href.
    // When the result came from the transcript pack search, we forward the
    // query (and the original character offset) so episode-viewer can scroll
    // straight to the matched sentence and highlight it.
    const params = new URLSearchParams({ file: episode.filename });
    const ctx = episode.searchContext;
    if (ctx && ctx.snippet) {
        const q = ctx.matchedWords && ctx.matchedWords[0];
        if (q) params.set('q', q);
        if (typeof ctx.snippet.offset === 'number') {
            params.set('offset', String(ctx.snippet.offset));
        }
    }
    article.href = `episode.html?${params.toString()}`;

    return article;
}

function renderPagination() {
    const totalPages = Math.ceil(state.filteredEpisodes.length / CONFIG.EPISODES_PER_PAGE);
    
    if (totalPages <= 1) {
        dom.paginationContainer.innerHTML = '';
        return;
    }
    
    dom.paginationContainer.innerHTML = '';
    
    // Previous button
    const prevBtn = document.createElement('button');
    prevBtn.textContent = '← Previous';
    prevBtn.disabled = state.currentPage === 1;
    prevBtn.addEventListener('click', () => goToPage(state.currentPage - 1));
    dom.paginationContainer.appendChild(prevBtn);
    
    // Page numbers
    const pageNumbers = getPageNumbers(state.currentPage, totalPages);
    pageNumbers.forEach(pageNum => {
        if (pageNum === '...') {
            const ellipsis = document.createElement('span');
            ellipsis.className = 'page-info';
            ellipsis.textContent = '...';
            dom.paginationContainer.appendChild(ellipsis);
        } else {
            const pageBtn = document.createElement('button');
            pageBtn.textContent = pageNum;
            pageBtn.className = pageNum === state.currentPage ? 'active' : '';
            pageBtn.addEventListener('click', () => goToPage(pageNum));
            dom.paginationContainer.appendChild(pageBtn);
        }
    });
    
    // Next button
    const nextBtn = document.createElement('button');
    nextBtn.textContent = 'Next →';
    nextBtn.disabled = state.currentPage === totalPages;
    nextBtn.addEventListener('click', () => goToPage(state.currentPage + 1));
    dom.paginationContainer.appendChild(nextBtn);
    
    // Page info
    const pageInfo = document.createElement('span');
    pageInfo.className = 'page-info';
    pageInfo.textContent = `Page ${state.currentPage} of ${totalPages}`;
    dom.paginationContainer.appendChild(pageInfo);
}

function getPageNumbers(current, total) {
    const delta = 2;
    const range = [];
    const rangeWithDots = [];
    let l;

    for (let i = 1; i <= total; i++) {
        if (i === 1 || i === total || (i >= current - delta && i <= current + delta)) {
            range.push(i);
        }
    }

    range.forEach((i) => {
        if (l) {
            if (i - l === 2) {
                rangeWithDots.push(l + 1);
            } else if (i - l !== 1) {
                rangeWithDots.push('...');
            }
        }
        rangeWithDots.push(i);
        l = i;
    });

    return rangeWithDots;
}

function goToPage(page) {
    const totalPages = Math.ceil(state.filteredEpisodes.length / CONFIG.EPISODES_PER_PAGE);
    
    if (page < 1 || page > totalPages) return;
    
    state.currentPage = page;
    renderEpisodes(true); // Scroll to top when changing pages
    renderPagination();
}

// ========================================
// UTILITIES
// ========================================
async function fetchWithTimeout(url, timeout) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);
    
    try {
        const response = await fetch(url, {
            signal: controller.signal,
            headers: {
                'Accept': 'application/json',
                'Accept-Encoding': 'br, gzip',
            },
            mode: 'cors',
            credentials: 'omit'
        });
        clearTimeout(timeoutId);
        return response;
    } catch (error) {
        clearTimeout(timeoutId);
        throw error;
    }
}

function handleUrlParams() {
    const params = new URLSearchParams(window.location.search);
    const query = params.get('q') || params.get('search');
    const mode = params.get('mode');
    
    if (mode === 'content') {
        // Switch to content search tab
        const contentTab = document.querySelector('[data-mode="content"]');
        if (contentTab) contentTab.click();
    }
    
    if (query) {
        if (state.currentSearchMode === 'content') {
            dom.contentSearchInput.value = query;
            // Wait for index to load before searching
            if (state.indices.core) {
                performContentSearch(query);
            } else {
                // Try again after core index loads
                setTimeout(() => {
                    if (state.indices.core) {
                        performContentSearch(query);
                    }
                }, 1000);
            }
        } else {
            dom.searchInput.value = query;
            handleNumberSearch();
        }
    }
}

// ========================================
// DISCLAIMER TOGGLE
// ========================================
function setupDisclaimerToggle() {
    const toggle = document.getElementById('disclaimer-toggle');
    const content = document.getElementById('disclaimer-content');
    const headerLink = document.getElementById('header-disclaimer-link');

    if (toggle && content) {
        toggle.addEventListener('click', (e) => {
            e.preventDefault();
            if (content.style.display === 'none') {
                content.style.display = 'block';
                toggle.textContent = '版權聲明 ▲';
            } else {
                content.style.display = 'none';
                toggle.textContent = '版權聲明';
            }
        });
    }

    // Header link: open footer disclaimer and scroll to it
    if (headerLink && content && toggle) {
        headerLink.addEventListener('click', (e) => {
            e.preventDefault();
            content.style.display = 'block';
            toggle.textContent = '版權聲明 ▲';
            content.scrollIntoView({ behavior: 'smooth', block: 'start' });
        });
    }
}

// ========================================
// DEBUG UTILITIES
// ========================================
window.gooayeDebug = {
    state,
    loadExtendedIndex,
    loadFullIndex,
    searchInIndex,
    getIndexStats: () => ({
        core: state.indices.core ? Object.keys(state.indices.core.word_index).length : 0,
        extended: state.indices.extended ? Object.keys(state.indices.extended.word_index).length : 0,
        full: state.indices.full ? Object.keys(state.indices.full.word_index).length : 0,
        loadTimes: state.indexLoadTimes
    })
};

// Initialize disclaimer toggle when page loads
document.addEventListener('DOMContentLoaded', setupDisclaimerToggle);