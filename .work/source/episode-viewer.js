// Simple markdown parser
function parseMarkdown(markdown) {
    let html = markdown;
    
    // Escape HTML
    html = html.replace(/&/g, '&amp;')
               .replace(/</g, '&lt;')
               .replace(/>/g, '&gt;');
    
    // Headers (must process from most # to fewest to avoid partial matches)
    html = html.replace(/^###### (.*$)/gim, '<h6>$1</h6>');
    html = html.replace(/^##### (.*$)/gim, '<h5>$1</h5>');
    html = html.replace(/^#### (.*$)/gim, '<h4>$1</h4>');
    html = html.replace(/^### (.*$)/gim, '<h3>$1</h3>');
    html = html.replace(/^## (.*$)/gim, '<h2>$1</h2>');
    html = html.replace(/^# (.*$)/gim, '<h1>$1</h1>');
    
    // Bold
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/__(.+?)__/g, '<strong>$1</strong>');
    
    // Italic
    html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
    html = html.replace(/_(.+?)_/g, '<em>$1</em>');
    
    // Links
    html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>');
    
    // Inline code
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
    
    // Code blocks
    html = html.replace(/```(.*?)\n([\s\S]*?)```/g, function(match, lang, code) {
        return '<pre><code>' + code.trim() + '</code></pre>';
    });
    
    // Blockquotes
    html = html.replace(/^&gt; (.*$)/gim, '<blockquote>$1</blockquote>');
    
    // Horizontal rules
    html = html.replace(/^---$/gim, '<hr>');
    html = html.replace(/^\*\*\*$/gim, '<hr>');
    
    // Lists
    html = html.replace(/^\* (.+)$/gim, '<li>$1</li>');
    html = html.replace(/^- (.+)$/gim, '<li>$1</li>');
    html = html.replace(/^\d+\. (.+)$/gim, '<li>$1</li>');
    
    // Wrap consecutive list items
    html = html.replace(/(<li>.*<\/li>\n?)+/g, function(match) {
        return '<ul>' + match + '</ul>';
    });
    
    // Paragraphs
    html = html.split('\n\n').map(paragraph => {
        paragraph = paragraph.trim();
        if (paragraph && 
            !paragraph.startsWith('<h') && 
            !paragraph.startsWith('<ul') && 
            !paragraph.startsWith('<ol') && 
            !paragraph.startsWith('<blockquote') &&
            !paragraph.startsWith('<pre') &&
            !paragraph.startsWith('<hr')) {
            // Convert single line breaks to <br> within paragraphs
            paragraph = paragraph.replace(/\n/g, '<br>');
            return '<p>' + paragraph + '</p>';
        }
        return paragraph;
    }).join('\n\n');
    
    // Add paragraph anchors for sharing functionality
    let pid = 0;
    html = html.replace(/<p>([\s\S]*?)<\/p>/g, (_, inner) => {
        pid += 1;
        return `<p id="p-${pid}" data-paragraph="true">${inner}</p>`;
    });
    
    return html;
}

// Load and display episode
async function loadEpisode() {
    const viewer = document.getElementById('episode-viewer');
    
    // Get filename from URL params
    const urlParams = new URLSearchParams(window.location.search);
    const filename = urlParams.get('file');
    
    if (!filename) {
        viewer.innerHTML = '<div class="error-message">No episode specified. <a href="index.html">Return to episodes list</a></div>';
        // Add noindex for error pages
        const metaRobots = document.createElement('meta');
        metaRobots.name = 'robots';
        metaRobots.content = 'noindex, nofollow';
        document.head.appendChild(metaRobots);
        return;
    }
    
    try {
        // First, load episodes data to get prev/next info
        const episodesResponse = await fetch('episodes.json', {
            mode: 'cors',
            credentials: 'omit',
            headers: {
                'Accept': 'application/json'
            }
        });
        const allEpisodes = await episodesResponse.json();
        
        // Find current episode and its neighbors
        // episodes.json is sorted ASCENDING (oldest first: EP1, EP2, ..., EP582, EP583)
        const currentIndex = allEpisodes.findIndex(ep => ep.filename === filename);
        const currentEpisode = currentIndex >= 0 ? allEpisodes[currentIndex] : null;

        // CORRECT LOGIC:
        // "Previous" button should go to OLDER episode (LOWER number)
        // In ascending array, older episodes are at LOWER indices
        const prevEpisode = currentIndex > 0 ? allEpisodes[currentIndex - 1] : null;
        
        // "Next" button should go to NEWER episode (HIGHER number)  
        // In ascending array, newer episodes are at HIGHER indices
        const nextEpisode = currentIndex < allEpisodes.length - 1 ? allEpisodes[currentIndex + 1] : null;
        
        // Fetch the markdown file (encode filename for emoji support)
        const response = await fetch(`episodes/${encodeURIComponent(filename)}`, {
            mode: 'cors',
            credentials: 'omit',
            headers: {
                'Accept': 'text/markdown, text/plain'
            }
        });
        
        if (!response.ok) {
            throw new Error('Episode not found');
        }
        
        const markdown = await response.text();
        
        // Extract episode number and title from filename
        const match = filename.match(/EP(\d+)[_｜]?(.*?)\.md$/);
        let episodeNumber = '';
        let episodeTitle = '';
        
        if (match) {
            episodeNumber = match[1];
            episodeTitle = match[2] || `Episode ${episodeNumber}`;
            
            // Clean up title
            if (episodeTitle.startsWith('transcript_')) {
                episodeTitle = episodeTitle.replace(/^transcript_[^_]+_[^_]+_/, '');
            }
            // Remove underscore prefix if present
            episodeTitle = episodeTitle.replace(/^_+/, '').trim();
        }

        // Prefer the curated display_title from episodes.json (handles emoji-only filenames)
        if (currentEpisode?.display_title) {
            episodeTitle = currentEpisode.display_title;
        }
        const episodeSummary = currentEpisode?.summary || '';
        
        // Parse and display
        const content = parseMarkdown(markdown);
        
        // Build navigation HTML
        const prevEpNum = prevEpisode ? (prevEpisode.filename.match(/EP(\d+)/)?.[1] || '') : '';
        const nextEpNum = nextEpisode ? (nextEpisode.filename.match(/EP(\d+)/)?.[1] || '') : '';

        const prevNavHTML = prevEpisode ?
            `<a href="episode.html?file=${encodeURIComponent(prevEpisode.filename)}" class="nav-link nav-prev" title="EP${prevEpNum}">
                <span class="nav-arrow">←</span>
                <span class="nav-text">Previous</span>
            </a>` :
            '<span class="nav-link nav-disabled" aria-disabled="true"><span class="nav-arrow">←</span><span class="nav-text">Previous</span></span>';

        const nextNavHTML = nextEpisode ?
            `<a href="episode.html?file=${encodeURIComponent(nextEpisode.filename)}" class="nav-link nav-next" title="EP${nextEpNum}">
                <span class="nav-text">Next</span>
                <span class="nav-arrow">→</span>
            </a>` :
            '<span class="nav-link nav-disabled" aria-disabled="true"><span class="nav-text">Next</span><span class="nav-arrow">→</span></span>';

        const homeNavHTML = `<a href="index.html" class="nav-link nav-home" title="All Episodes">
                <span class="nav-icon">⊞</span>
                <span class="nav-text">All Episodes</span>
            </a>`;

        const navStrip = (extraClass) => `
            <nav class="ep-nav ${extraClass}" aria-label="Episode navigation">
                ${prevNavHTML}
                ${homeNavHTML}
                ${nextNavHTML}
            </nav>`;

        viewer.innerHTML = `
            <!-- Breadcrumb Navigation -->
            <nav class="breadcrumb" aria-label="Breadcrumb">
                <a href="index.html">股癌逐字稿</a>
                <span class="breadcrumb-separator">›</span>
                <span class="breadcrumb-current">EP${episodeNumber}</span>
            </nav>

            <article class="episode-content">
                <header class="episode-head">
                    <h1 class="episode-title-h1">${episodeTitle}</h1>
                </header>

                ${navStrip('ep-nav-top')}

                <div class="episode-body">
                    ${content}
                </div>
            </article>

            ${navStrip('ep-nav-bottom')}

            <!-- Episode footer: meta + actions + disclaimer -->
            <footer class="episode-footer">
                <div class="episode-footer-row">
                    <span class="footer-item">原版 Podcast <a href="https://linktr.ee/gooaye" target="_blank" rel="noopener noreferrer" title="Gooaye Linktree">🌳</a></span>
                    <span class="footer-sep">·</span>
                    <button id="share-episode" class="btn-share-link" type="button">分享本集</button>
                    <span class="footer-sep">·</span>
                    <a href="#" id="disclaimer-toggle-top" title="版權聲明">版權聲明</a>
                </div>
                <div class="episode-footer-meta">
                    Fan-created transcript archive. Not affiliated with Gooaye Podcast.
                </div>
                <div id="disclaimer-content-top" class="disclaimer-content" style="display: none;">
                    <div class="disclaimer-section">
                        <h3>免責與版權聲明</h3>
                        <p>本網站所提供之逐字稿內容，係依據公開可收聽之《股癌》Podcast 音訊，透過人工智慧轉譯、人工修正與格式化整理而成。原始音訊內容（包括其中的文字、語音表達與想法）之著作權，均屬《股癌》Podcast 節目製作人及相關權利人所有。</p>
                        <p>本網站對逐字稿的加工處理（如轉錄、修正與排版），僅作為學習與交流之用途，完全非商業性質，亦無意取代原節目。正確內容請以《股癌》Podcast 原始音訊為準。</p>
                        <p>如原節目製作人或相關權利人認為本網站內容有侵權之虞或不適當，本網站將於接獲通知後，立即配合修改或移除相關內容。</p>
                    </div>
                    <div class="disclaimer-section">
                        <h3>Disclaimer and Copyright Notice</h3>
                        <p>The transcripts provided on this website are derived from publicly available audio content of the "Gooaye" Podcast. They are processed through AI transcription, manual corrections, and formatting. All copyrights for the original audio content — including its text, spoken expressions, and ideas — belong to the creators and rights holders of the "Gooaye" Podcast.</p>
                        <p>Our processing of the transcripts (including transcription, correction, and formatting) is intended solely for learning and non-commercial purposes, and is not intended to replace the original program. For accurate content, please refer to the original audio of the "Gooaye" Podcast.</p>
                        <p>If the original creators or rights holders believe that any content on this website infringes upon their rights or is otherwise inappropriate, we will promptly modify or remove such content upon notification.</p>
                    </div>
                </div>
            </footer>
            
            <!-- Floating Share Toolbar (hidden by default) -->
            <div id="share-toolbar" class="share-toolbar" role="menu" aria-hidden="true">
                <button data-act="copy">Copy</button>
                <button data-act="modal">分享至</button>
            </div>
            
            <!-- Text Share Modal -->
            <div id="share-modal" class="share-modal">
                <div class="share-modal-content">
                    <h3>分享選取文字</h3>
                    <div class="share-preview" id="share-preview"></div>
                    <div class="share-options">
                        <button class="share-option" data-platform="twitter">
                            <div class="share-option-icon">𝕏</div>
                            <div>X / Twitter</div>
                        </button>
                        <button class="share-option" data-platform="threads">
                            <div class="share-option-icon">@</div>
                            <div>Threads</div>
                        </button>
                        <button class="share-option" data-platform="facebook">
                            <div class="share-option-icon">f</div>
                            <div>Facebook</div>
                        </button>
                        <button class="share-option" data-platform="instagram">
                            <div class="share-option-icon">📷</div>
                            <div>Instagram Stories</div>
                        </button>
                        <button class="share-option" data-platform="copy">
                            <div class="share-option-icon">📋</div>
                            <div>複製連結</div>
                        </button>
                    </div>
                    <div class="share-modal-actions">
                        <button class="share-modal-close">取消</button>
                    </div>
                </div>
            </div>
            
            <!-- Episode Share Modal -->
            <div id="episode-share-modal" class="share-modal">
                <div class="share-modal-content">
                    <h3>分享全集</h3>
                    <div class="share-preview" id="episode-share-preview"></div>
                    <div class="share-options">
                        <button class="share-option" data-platform="twitter">
                            <div class="share-option-icon">𝕏</div>
                            <div>X / Twitter</div>
                        </button>
                        <button class="share-option" data-platform="threads">
                            <div class="share-option-icon">@</div>
                            <div>Threads</div>
                        </button>
                        <button class="share-option" data-platform="facebook">
                            <div class="share-option-icon">f</div>
                            <div>Facebook</div>
                        </button>
                        <button class="share-option" data-platform="copy">
                            <div class="share-option-icon">📋</div>
                            <div>複製連結</div>
                        </button>
                    </div>
                    <div class="share-modal-actions">
                        <button class="share-modal-close">取消</button>
                    </div>
                </div>
            </div>
            
            <!-- Instagram Guide Modal -->
            <div id="instagram-guide-modal" class="share-modal">
                <div class="share-modal-content">
                    <h3>🎨 Instagram Stories 分享</h3>
                    <div class="instagram-guide">
                        <p>✅ <strong>引用圖片已下載</strong></p>
                        <p>✅ <strong>連結已複製到剪貼簿</strong></p>
                        <div class="instagram-steps">
                            <h4>接下來請：</h4>
                            <ol>
                                <li>打開 Instagram 應用程式</li>
                                <li>點擊左上角相機圖示創建 Stories</li>
                                <li>選擇剛下載的引用圖片</li>
                                <li>貼上連結（長按輸入框選擇「貼上」）</li>
                                <li>分享到你的 Stories！</li>
                            </ol>
                        </div>
                    </div>
                    <div class="share-modal-actions">
                        <button class="share-modal-close">完成</button>
                    </div>
                </div>
            </div>
            
            <!-- Mobile Screenshot Share Guide Modal -->
            <div id="mobile-screenshot-guide-modal" class="share-modal">
                <div class="share-modal-content">
                    <h3>📱 截圖分享到 Instagram</h3>
                    <div class="instagram-guide">
                        <p>✅ <strong>連結已複製到剪貼簿</strong></p>
                        <div class="instagram-steps">
                            <h4>請按照以下步驟：</h4>
                            <ol>
                                <li>📱 <strong>立即截圖此頁面</strong><br>
                                    <small>iPhone: 電源鍵 + 音量上鍵<br>
                                    Android: 電源鍵 + 音量下鍵</small>
                                </li>
                                <li>📝 <strong>編輯截圖</strong>（可選）<br>
                                    <small>標註重點、裁切內容等</small>
                                </li>
                                <li>📤 <strong>打開 Instagram</strong><br>
                                    <small>點擊左上角相機圖示或滑動進入 Stories</small>
                                </li>
                                <li>🖼️ <strong>選擇剛截的圖</strong><br>
                                    <small>從相簿選擇剛才的截圖</small>
                                </li>
                                <li>🔗 <strong>加入連結</strong><br>
                                    <small>點擊右上角貼紙，選擇「連結」，長按貼上</small>
                                </li>
                                <li>🚀 <strong>發布 Stories</strong><br>
                                    <small>讓朋友看到這個精彩內容！</small>
                                </li>
                            </ol>
                            <div style="margin-top: 1rem; padding: 1rem; background: #f0f8ff; border-radius: 8px; border-left: 4px solid #2196f3;">
                                <strong>💡 小技巧</strong><br>
                                可以用手機的分享功能直接分享截圖，然後在 Instagram Stories 中貼上連結！
                            </div>
                        </div>
                    </div>
                    <div class="share-modal-actions">
                        <button class="share-modal-close" id="instagram-guide-close">我知道了</button>
                        <button class="share-modal-close" onclick="window.open('https://instagram.com', '_blank')" style="background: linear-gradient(45deg, #f09433 0%,#e6683c 25%,#dc2743 50%,#cc2366 75%,#bc1888 100%); color: white; border: none;">
                            📱 打開 Instagram
                        </button>
                    </div>
                </div>
            </div>
        `;
        
        // Update page title
        document.title = `股癌逐字稿 EP${episodeNumber}：${episodeTitle}`;
        
        // Add canonical URL
        const canonicalUrl = `https://whatmkreallysaid.com/episodes/ep${episodeNumber}`;
        let canonicalLink = document.querySelector('link[rel="canonical"]');
        if (!canonicalLink) {
            canonicalLink = document.createElement('link');
            canonicalLink.rel = 'canonical';
            document.head.appendChild(canonicalLink);
        }
        canonicalLink.href = canonicalUrl;
        
        // Add structured data for SEO
        addStructuredData(episodeNumber, episodeTitle, filename);
        
        // Add Open Graph meta tags for social sharing
        addOpenGraphMetaTags(episodeNumber, episodeTitle, filename, episodeSummary);
        
        // Setup top disclaimer toggle after content is loaded
        setupTopDisclaimerToggle();
        
        // Initialize sharing functionality after content is loaded
        initShareToolbar();
        initShareModal();
        initShareEpisode();
        initMobileScreenshotShare();
        
        // Highlight shared paragraph if URL has anchor
        highlightFromHash();

        // Highlight + scroll-to search query if user came from a search hit.
        // ?q=秋口幹你娘 highlights all occurrences and scrolls to the first.
        // ?offset=N optionally biases towards the Nth-character-region paragraph.
        highlightSearchQuery(urlParams.get('q'), urlParams.get('offset'));

    } catch (error) {
        console.error('Error loading episode:', error);
        viewer.innerHTML = `
            <div class="error-message">
                <p>Error loading episode.</p>
                <p><a href="index.html">Return to episodes list</a></p>
            </div>
        `;
        // Add noindex for error pages
        const metaRobots = document.createElement('meta');
        metaRobots.name = 'robots';
        metaRobots.content = 'noindex, nofollow';
        document.head.appendChild(metaRobots);
    }
}

// Setup bottom disclaimer toggle
function setupDisclaimerToggle() {
    const toggleBottom = document.getElementById('disclaimer-toggle');
    const contentBottom = document.getElementById('disclaimer-content');
    
    if (toggleBottom && contentBottom) {
        toggleBottom.addEventListener('click', (e) => {
            e.preventDefault();
            if (contentBottom.style.display === 'none') {
                contentBottom.style.display = 'block';
                toggleBottom.textContent = '版權聲明 ▲';
            } else {
                contentBottom.style.display = 'none';
                toggleBottom.textContent = '版權聲明';
            }
        });
    }
}

// Setup top disclaimer toggle (inside episode content)
function setupTopDisclaimerToggle() {
    const toggleTop = document.getElementById('disclaimer-toggle-top');
    const contentTop = document.getElementById('disclaimer-content-top');
    
    if (toggleTop && contentTop) {
        toggleTop.addEventListener('click', (e) => {
            e.preventDefault();
            if (contentTop.style.display === 'none') {
                contentTop.style.display = 'block';
                toggleTop.textContent = '版權聲明 ▲';
            } else {
                contentTop.style.display = 'none';
                toggleTop.textContent = '版權聲明';
            }
        });
    }
}

// Highlight shared paragraph from URL hash
function highlightFromHash() {
    const id = location.hash.slice(1);
    if (!id) return;
    const el = document.getElementById(id);
    if (el) {
        el.classList.add('share-highlight');
        el.scrollIntoView({ behavior: 'smooth', block: 'start' });
        setTimeout(() => el.classList.remove('share-highlight'), 2500);
    }
}

// Add structured data for SEO
function addStructuredData(episodeNumber, episodeTitle, filename) {
    // Remove any existing structured data
    const existingScript = document.getElementById('episode-structured-data');
    if (existingScript) {
        existingScript.remove();
    }
    
    // Create structured data for the episode
    const structuredData = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": `股癌逐字稿 EP${episodeNumber}：${episodeTitle}`,
        "name": `股癌逐字稿 EP${episodeNumber}`,
        "description": `股癌Podcast EP${episodeNumber} 完整逐字稿 - ${episodeTitle}。由AI聽寫並經修正，方便搜尋與閱讀。`,
        "url": `https://whatmkreallysaid.com/episode.html?file=${encodeURIComponent(filename)}`,
        "datePublished": new Date().toISOString().split('T')[0], // We could enhance this with actual episode dates
        "dateModified": new Date().toISOString().split('T')[0],
        "author": {
            "@type": "Organization",
            "name": "股癌非官方逐字稿"
        },
        "publisher": {
            "@type": "Organization",
            "name": "股癌非官方逐字稿",
            "url": "https://whatmkreallysaid.com/"
        },
        "inLanguage": "zh-TW",
        "isPartOf": {
            "@type": "WebSite",
            "name": "股癌逐字稿全集",
            "url": "https://whatmkreallysaid.com/"
        },
        "breadcrumb": {
            "@type": "BreadcrumbList",
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": 1,
                    "name": "股癌逐字稿全集",
                    "item": "https://whatmkreallysaid.com/"
                },
                {
                    "@type": "ListItem",
                    "position": 2,
                    "name": `EP${episodeNumber}`,
                    "item": `https://whatmkreallysaid.com/episode.html?file=${encodeURIComponent(filename)}`
                }
            ]
        }
    };
    
    // Add the structured data to the page
    const script = document.createElement('script');
    script.type = 'application/ld+json';
    script.id = 'episode-structured-data';
    script.textContent = JSON.stringify(structuredData, null, 2);
    document.head.appendChild(script);
}

// Add Open Graph meta tags for better social sharing
function addOpenGraphMetaTags(episodeNumber, episodeTitle, filename, episodeSummary) {
    // Remove any existing OG tags
    const existingOgTags = document.querySelectorAll('meta[property^="og:"], meta[name^="twitter:"]');
    existingOgTags.forEach(tag => tag.remove());
    
    const description = episodeSummary
        ? `股癌Podcast EP${episodeNumber}：${episodeSummary}`
        : `股癌Podcast EP${episodeNumber} 完整逐字稿 - ${episodeTitle}。支援全文搜尋與段落分享。`;
    const ogTags = [
        { property: 'og:type', content: 'article' },
        { property: 'og:title', content: `股癌逐字稿 EP${episodeNumber}｜${episodeTitle}` },
        { property: 'og:description', content: description },
        { property: 'og:url', content: `https://whatmkreallysaid.com/episode.html?file=${encodeURIComponent(filename)}` },
        { property: 'og:site_name', content: '股癌非官方逐字稿' },
        { name: 'twitter:card', content: 'summary_large_image' },
        { name: 'twitter:title', content: `股癌逐字稿 EP${episodeNumber}｜${episodeTitle}` },
        { name: 'twitter:description', content: description }
    ];
    
    ogTags.forEach(tagData => {
        const meta = document.createElement('meta');
        if (tagData.property) {
            meta.setAttribute('property', tagData.property);
        } else if (tagData.name) {
            meta.setAttribute('name', tagData.name);
        }
        meta.setAttribute('content', tagData.content);
        document.head.appendChild(meta);
    });
}

// --- SHARING FUNCTIONALITY ---

// Helper functions
function isMobile() {
    return /iPhone|iPad|iPod|Android/i.test(navigator.userAgent);
}

function trimForPlatform(s, limit) {
    if (s.length <= limit) return s;
    return s.slice(0, limit - 1) + '…';
}

function getEpisodeMeta() {
    const h1 = document.querySelector('.episode-main-title')?.textContent?.trim() || document.title;
    const epMatch = h1.match(/EP(\d+)/i);
    const ep = epMatch ? epMatch[1] : '';
    const canonical = document.querySelector('link[rel="canonical"]')?.href || location.href;
    return { h1, ep, canonical };
}

function getSelectedQuoteAndAnchor() {
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed) return null;
    const text = sel.toString().trim().replace(/\s+/g, ' ');
    
    // Try to find paragraph from both anchor and focus nodes
    let paragraph = null;
    
    // Check anchor node
    let node = sel.anchorNode;
    while (node && node.nodeType !== 1) {
        node = node.parentNode;
    }
    if (node) {
        paragraph = node.closest('p[data-paragraph="true"]');
    }
    
    // If not found, check focus node
    if (!paragraph) {
        node = sel.focusNode;
        while (node && node.nodeType !== 1) {
            node = node.parentNode;
        }
        if (node) {
            paragraph = node.closest('p[data-paragraph="true"]');
        }
    }
    
    // If still not found, check if selection contains any paragraph
    if (!paragraph && sel.rangeCount > 0) {
        const range = sel.getRangeAt(0);
        const commonAncestor = range.commonAncestorContainer;
        if (commonAncestor.nodeType === 1) {
            paragraph = commonAncestor.querySelector('p[data-paragraph="true"]');
        } else {
            let parent = commonAncestor.parentNode;
            while (parent && parent.nodeType === 1) {
                paragraph = parent.closest('p[data-paragraph="true"]');
                if (paragraph) break;
                parent = parent.parentNode;
            }
        }
    }
    
    const anchorId = paragraph?.id || null;
    return { text, anchorId };
}

function buildDeepLink(anchorId) {
    const url = new URL(location.href);
    url.hash = anchorId ? `#${anchorId}` : '';
    return url.toString();
}

// Web Share API support check
function canNativeShare() { 
    return !!navigator.share; 
}

// Share URL builders
const Share = {
    threads(text, url) {
        const q = new URLSearchParams({ text: `${text}\n${url}` });
        return `https://www.threads.net/intent/post?${q.toString()}`;
    },
    twitter(text, url) {
        const q = new URLSearchParams({ text, url });
        return `https://twitter.com/intent/tweet?${q.toString()}`;
    },
    facebook(url) {
        const q = new URLSearchParams({ u: url });
        return `https://www.facebook.com/sharer/sharer.php?${q.toString()}`;
    }
};

// Store current share data
let currentShareData = null;
let currentEpisodeShareData = null;
let selectionTimeout = null;

// Initialize floating toolbar for text selection sharing
function initShareToolbar() {
    const toolbar = document.getElementById('share-toolbar');
    if (!toolbar) {
        return;
    }

    document.addEventListener('selectionchange', () => {
        // Clear previous timeout to debounce rapid selection changes
        if (selectionTimeout) {
            clearTimeout(selectionTimeout);
        }
        
        selectionTimeout = setTimeout(() => {
            const sel = window.getSelection();
            if (!sel || sel.isCollapsed) { 
                toolbar.style.display = 'none'; 
                return; 
            }
            
            const text = sel.toString().trim();
            if (!text || text.length < 3) {
                toolbar.style.display = 'none';
                return;
            }
            
            try {
                const range = sel.getRangeAt(0);
                const rect = range.getBoundingClientRect();
                
                if (rect.width === 0 && rect.height === 0) {
                    return;
                }
                
                // Position toolbar below selection on mobile, above on desktop
                const isMobileDevice = isMobile();
                const toolbarWidth = 200;
                const toolbarHeight = 50;
                
                let left, top;
                
                if (isMobileDevice) {
                    // On mobile: position below selection to avoid iOS/Android native toolbar conflict
                    left = Math.max(8, Math.min(rect.left + (rect.width - toolbarWidth) / 2, window.innerWidth - toolbarWidth - 8));
                    top = Math.min(rect.bottom + 10, window.innerHeight - toolbarHeight - 8);
                    
                    // If there's not enough space below, try above (but further away)
                    if (top + toolbarHeight > window.innerHeight - 20) {
                        top = Math.max(8, rect.top - toolbarHeight - 20);
                    }
                } else {
                    // On desktop: position above selection (original behavior)
                    left = Math.max(8, Math.min(rect.left, window.innerWidth - toolbarWidth - 8));
                    top = Math.max(8, Math.min(rect.top - toolbarHeight - 10, window.innerHeight - toolbarHeight - 8));
                }
                
                toolbar.style.position = 'fixed';
                toolbar.style.left = `${left}px`;
                toolbar.style.top = `${top}px`;
                toolbar.style.display = 'flex';
                toolbar.style.zIndex = '9999';
                toolbar.setAttribute('aria-hidden', 'false');
                
            } catch (error) {
                // Silently handle positioning errors
            }
        }, 100); // 100ms debounce
    });

    document.addEventListener('click', (e) => {
        if (!toolbar.contains(e.target) && !document.getElementById('share-modal').contains(e.target)) {
            const sel = window.getSelection();
            if (!sel || sel.isCollapsed) {
                toolbar.style.display = 'none';
                toolbar.setAttribute('aria-hidden', 'true');
            }
        }
    });

    // Handle both click and touch events for better mobile support
    const handleToolbarAction = async (e) => {
        e.preventDefault();
        e.stopPropagation();
        
        if (e.target.tagName !== 'BUTTON') return;
        
        // Get selection data immediately before it might get cleared
        const act = e.target.dataset.act;
        const meta = getEpisodeMeta();
        const selData = getSelectedQuoteAndAnchor();
        if (!selData) return;
        
        const { text, anchorId } = selData;
        
        // Clear selection after a tiny delay to ensure button interaction works
        setTimeout(() => clearTextSelection(), 50);
        
        // Build message
        const deepLink = buildDeepLink(anchorId);
        const base = `「${trimForPlatform(text, 220)}」\n— 股癌 EP${meta.ep}｜全文：${deepLink}`;
        
        // Store for modal use
        currentShareData = {
            text, anchorId, deepLink, base, meta,
            fullText: `「${text}」\n— 股癌 EP${meta.ep}｜全文：${deepLink}`
        };
        
        // Actions
        if (act === 'copy') {
            try {
                await navigator.clipboard.writeText(base);
                e.target.textContent = 'Copied!';
                setTimeout(()=> e.target.textContent='Copy', 1500);
            } catch (error) {
                // Fallback for mobile
                alert('Text copied: ' + base);
            }
            return;
        }
        if (act === 'modal') {
            showTextShareModal();
            return;
        }
    };
    
    toolbar.addEventListener('click', handleToolbarAction);
    toolbar.addEventListener('touchend', handleToolbarAction);
}

// Show text share modal
function showTextShareModal() {
    if (!currentShareData) return;
    
    const modal = document.getElementById('share-modal');
    const preview = document.getElementById('share-preview');
    
    if (!modal || !preview) return;
    
    preview.textContent = currentShareData.fullText;
    modal.style.display = 'flex';
    modal.style.zIndex = '9999';
    
    // Hide toolbar when modal opens
    const toolbar = document.getElementById('share-toolbar');
    if (toolbar) {
        toolbar.style.display = 'none';
    }
    
    // Clear text selection to avoid mobile interaction issues
    clearTextSelection();
}

// Clear text selection helper function
function clearTextSelection() {
    if (window.getSelection) {
        const selection = window.getSelection();
        if (selection.removeAllRanges) {
            selection.removeAllRanges();
        } else if (selection.empty) {
            selection.empty();
        }
    }
}

// Show episode share modal
function showEpisodeShareModal() {
    const meta = getEpisodeMeta();
    const text = `股癌逐字稿 EP${meta.ep}｜${meta.h1.replace(/^股癌逐字稿\s+EP\d+\s*/,'')}`;
    
    currentEpisodeShareData = {
        title: meta.h1,
        text,
        url: meta.canonical
    };
    
    const modal = document.getElementById('episode-share-modal');
    const preview = document.getElementById('episode-share-preview');
    
    preview.textContent = `${text}\n${meta.canonical}`;
    modal.style.display = 'flex';
}

// Initialize share modal
function initShareModal() {
    // Initialize text share modal
    initTextShareModal();
    // Initialize episode share modal
    initEpisodeShareModal();
    // Initialize Instagram guide modal
    initInstagramGuideModal();
}

// Initialize text share modal
function initTextShareModal() {
    const modal = document.getElementById('share-modal');
    if (!modal) {
        console.warn('Text share modal element not found');
        return;
    }
    const closeBtn = modal.querySelector('.share-modal-close');
    if (!closeBtn) {
        console.warn('Text share modal close button not found');
        return;
    }
    
    // Close modal on background click
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            modal.style.display = 'none';
        }
    });
    
    // Close modal on close button
    closeBtn.addEventListener('click', () => {
        modal.style.display = 'none';
    });
    
    // Handle platform selection for text sharing
    modal.addEventListener('click', async (e) => {
        if (!e.target.matches('.share-option') && !e.target.closest('.share-option')) return;
        
        const option = e.target.closest('.share-option');
        const platform = option.dataset.platform;
        
        if (!currentShareData) return;
        
        const { text, deepLink, meta } = currentShareData;
        
        switch (platform) {
            case 'twitter':
                window.open(Share.twitter(`「${trimForPlatform(text, 240)}」 — 股癌 EP${meta.ep}`, deepLink), '_blank', 'noopener');
                break;
            case 'threads':
                window.open(Share.threads(`「${trimForPlatform(text, 300)}」 — 股癌 EP${meta.ep}`, deepLink), '_blank', 'noopener');
                break;
            case 'facebook':
                // Facebook doesn't support text in URL, so copy text to clipboard first
                navigator.clipboard.writeText(`「${text}」\n— 股癌 EP${meta.ep}｜全文：${deepLink}`);
                // Show user instruction
                alert('📋 引文已複製到剪貼簿！\n請在 Facebook 分享頁面中貼上內容。');
                window.open(Share.facebook(deepLink), '_blank', 'noopener');
                break;
            case 'instagram':
                await handleInstagramShare(text, deepLink, meta);
                break;
            case 'copy':
                await navigator.clipboard.writeText(currentShareData.fullText);
                option.innerHTML = '<div class="share-option-icon">✅</div><div>已複製</div>';
                setTimeout(() => {
                    option.innerHTML = '<div class="share-option-icon">📋</div><div>複製連結</div>';
                }, 1500);
                break;
        }
        
        // Close modal after action (except for copy and instagram)
        if (platform !== 'copy' && platform !== 'instagram') {
            modal.style.display = 'none';
        }
    });
    
    // Close on Escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && modal.style.display === 'flex') {
            modal.style.display = 'none';
        }
    });
}

// Initialize "Share episode" button
function initShareEpisode() {
    // Check if share episode button exists
    const shareBtn = document.getElementById('share-episode');
    if (!shareBtn) {
        console.warn('Share episode button not found');
        return;
    }
    
    document.addEventListener('click', async (e) => {
        if (e.target?.id !== 'share-episode') return;
        showEpisodeShareModal();
    });
}

// Initialize episode share modal
function initEpisodeShareModal() {
    const modal = document.getElementById('episode-share-modal');
    if (!modal) {
        console.warn('Episode share modal element not found');
        return;
    }
    const closeBtn = modal.querySelector('.share-modal-close');
    if (!closeBtn) {
        console.warn('Episode share modal close button not found');
        return;
    }
    
    // Close modal on background click
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            modal.style.display = 'none';
        }
    });
    
    // Close modal on close button
    closeBtn.addEventListener('click', () => {
        modal.style.display = 'none';
    });
    
    // Handle platform selection for episode sharing
    modal.addEventListener('click', async (e) => {
        if (!e.target.matches('.share-option') && !e.target.closest('.share-option')) return;
        
        const option = e.target.closest('.share-option');
        const platform = option.dataset.platform;
        
        if (!currentEpisodeShareData) return;
        
        const { text, url } = currentEpisodeShareData;
        
        switch (platform) {
            case 'twitter':
                window.open(Share.twitter(text, url), '_blank', 'noopener');
                break;
            case 'threads':
                window.open(Share.threads(text, url), '_blank', 'noopener');
                break;
            case 'facebook':
                window.open(Share.facebook(url), '_blank', 'noopener');
                break;
            case 'copy':
                await navigator.clipboard.writeText(`${text}\n${url}`);
                option.innerHTML = '<div class="share-option-icon">✅</div><div>已複製</div>';
                setTimeout(() => {
                    option.innerHTML = '<div class="share-option-icon">📋</div><div>複製連結</div>';
                }, 1500);
                break;
        }
        
        // Close modal after action (except for copy)
        if (platform !== 'copy') {
            modal.style.display = 'none';
        }
    });
    
    // Close on Escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && modal.style.display === 'flex') {
            modal.style.display = 'none';
        }
    });
}

// Initialize Instagram guide modal
function initInstagramGuideModal() {
    const modal = document.getElementById('instagram-guide-modal');
    if (!modal) {
        console.warn('Instagram guide modal element not found');
        return;
    }
    const closeBtn = modal.querySelector('.share-modal-close');
    if (!closeBtn) {
        console.warn('Instagram guide modal close button not found');
        return;
    }
    
    // Close modal on background click
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            modal.style.display = 'none';
        }
    });
    
    // Close modal on close button
    closeBtn.addEventListener('click', () => {
        modal.style.display = 'none';
    });
    
    // Close on Escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && modal.style.display === 'flex') {
            modal.style.display = 'none';
        }
    });
}

// Initialize mobile screenshot guide modal
function initMobileScreenshotGuideModal() {
    const modal = document.getElementById('mobile-screenshot-guide-modal');
    if (!modal) {
        console.warn('Mobile screenshot guide modal element not found');
        return;
    }
    const closeBtn = modal.querySelector('.share-modal-close');
    if (!closeBtn) {
        console.warn('Mobile screenshot guide modal close button not found');
        return;
    }
    
    // Close modal on background click
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            modal.style.display = 'none';
        }
    });
    
    // Close modal on close button
    closeBtn.addEventListener('click', () => {
        modal.style.display = 'none';
    });
    
    // Close on Escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && modal.style.display === 'flex') {
            modal.style.display = 'none';
        }
    });
    
    // Auto-close modal when user takes screenshot (detect visibility change)
    document.addEventListener('visibilitychange', () => {
        if (document.hidden && modal.style.display === 'flex') {
            // User likely took screenshot or switched apps
            setTimeout(() => {
                if (modal.style.display === 'flex') {
                    modal.style.display = 'none';
                }
            }, 1000); // Small delay to allow screenshot
        }
    });
}

// Initialize mobile screenshot sharing
function initMobileScreenshotShare() {
    // Wait for DOM to be ready before accessing elements
    const initButton = () => {
        const mobileBtn = document.getElementById('mobile-screenshot-share');
        if (!mobileBtn) {
            // Retry in 100ms if button not found
            setTimeout(initButton, 100);
            return;
        }
        
        // Show button only on mobile devices
        const isMobileDevice = isMobile();
        if (isMobileDevice) {
            mobileBtn.style.display = 'inline-block';
        }
        
        // Handle mobile screenshot share button click
        mobileBtn.addEventListener('click', handleMobileScreenshotShare);
        mobileBtn.addEventListener('touchend', handleMobileScreenshotShare);
    };
    
    // Initialize the guide modal
    initMobileScreenshotGuideModal();
    
    // Start button initialization
    initButton();
}

// Handle mobile screenshot sharing
async function handleMobileScreenshotShare(e) {
    e.preventDefault();
    e.stopPropagation();
    
    try {
        // Get current episode info
        const meta = getEpisodeMeta();
        const url = meta.canonical || location.href;
        
        // Copy link to clipboard first
        await navigator.clipboard.writeText(url);
        
        // Check if Web Share API is available (better for mobile)
        if (navigator.share && isMobile()) {
            // Show brief instruction then trigger native share
            showMobileShareInstructions();
            
            // Wait a moment for user to read, then trigger native share
            setTimeout(async () => {
                try {
                    await navigator.share({
                        title: meta.h1 || document.title,
                        text: '📱 請截圖後分享到 Instagram Stories 並貼上連結！',
                        url: url
                    });
                } catch (shareError) {
                    // This is normal if user cancels
                }
            }, 2000);
            
        } else {
            showMobileScreenshotGuide();
        }
        
    } catch (error) {
        // Fallback: show manual instructions
        showMobileScreenshotGuide();
    }
}

// Show mobile share instructions (brief overlay)
function showMobileShareInstructions() {
    // Create temporary instruction overlay
    const overlay = document.createElement('div');
    overlay.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: rgba(0,0,0,0.8);
        color: white;
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 99999;
        font-size: 18px;
        text-align: center;
        padding: 2rem;
    `;
    
    overlay.innerHTML = `
        <div>
            <div style="font-size: 48px; margin-bottom: 1rem;">📱</div>
            <div><strong>連結已複製！</strong></div>
            <div style="margin: 1rem 0;">準備開啟分享選單...</div>
            <div style="font-size: 14px; opacity: 0.8;">取消分享後，請截圖並貼到 Instagram Stories</div>
        </div>
    `;
    
    document.body.appendChild(overlay);
    
    // Auto-remove after 4 seconds
    setTimeout(() => {
        if (document.body.contains(overlay)) {
            document.body.removeChild(overlay);
        }
    }, 4000);
}

// Show mobile screenshot guide modal
function showMobileScreenshotGuide() {
    const modal = document.getElementById('mobile-screenshot-guide-modal');
    if (modal) {
        modal.style.display = 'flex';
        modal.style.zIndex = '9999';
    } else {
        // Fallback alert
        alert('🔗 連結已複製到剪貼簿！\n\n📱 請截圖此頁面\n📤 分享到 Instagram Stories\n🔗 貼上連結');
    }
}

// Handle Instagram sharing with quote card generation
async function handleInstagramShare(text, deepLink, meta) {
    try {
        // Generate quote card
        const imageBlob = await generateQuoteCard(text, meta.ep, deepLink);
        
        // Download the image
        const url = URL.createObjectURL(imageBlob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `股癌-EP${meta.ep}-引用.png`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        
        // Copy link to clipboard
        await navigator.clipboard.writeText(deepLink);
        
        // Close text sharing modal
        const textModal = document.getElementById('share-modal');
        if (textModal) {
            textModal.style.display = 'none';
        }
        
        // Show Instagram guide modal
        const guideModal = document.getElementById('instagram-guide-modal');
        if (guideModal) {
            guideModal.style.display = 'flex';
        }
        
    } catch (error) {
        alert('⚠️ 產生引用圖片時發生錯誤，請再試一次。');
    }
}

// Generate quote card using Canvas
async function generateQuoteCard(text, episodeNumber, deepLink) {
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    
    // Canvas dimensions (Instagram Stories: 1080x1920)
    const width = 1080;
    const height = 1920;
    canvas.width = width;
    canvas.height = height;
    
    // Background gradient
    const gradient = ctx.createLinearGradient(0, 0, 0, height);
    gradient.addColorStop(0, '#faf7f2');
    gradient.addColorStop(1, '#f0ebe2');
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, width, height);
    
    // Title area
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillStyle = '#0f0f0f';
    ctx.font = 'bold 52px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans CJK TC", sans-serif';
    const title = `股癌 EP${episodeNumber}`;
    ctx.fillText(title, width / 2, 200);
    
    // Quote text with proper Chinese text wrapping
    ctx.font = '42px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans CJK TC", sans-serif';
    ctx.fillStyle = '#2c2c2c';
    
    // Improved text wrapping with proper side margins
    const maxWidth = width - 160; // 80px padding on each side
    const lineHeight = 65; // Increased for better readability
    const lines = [];
    let currentLine = '';
    
    // Handle both Chinese and English text properly
    for (let i = 0; i < text.length; i++) {
        const char = text[i];
        const testLine = currentLine + char;
        const metrics = ctx.measureText(testLine);
        
        if (metrics.width > maxWidth && currentLine.length > 0) {
            // Smart breaking for Chinese/English mixed text
            if (char === ' ' || currentLine.endsWith(' ') || 
                /[\u4e00-\u9fff]/.test(char) || /[\u4e00-\u9fff]/.test(currentLine.slice(-1))) {
                lines.push(currentLine.trim());
                currentLine = char === ' ' ? '' : char;
            } else {
                // Look back for a space to break English words properly
                let breakPoint = currentLine.lastIndexOf(' ');
                if (breakPoint > 0) {
                    lines.push(currentLine.substring(0, breakPoint).trim());
                    currentLine = currentLine.substring(breakPoint + 1) + char;
                } else {
                    lines.push(currentLine);
                    currentLine = char;
                }
            }
        } else {
            currentLine = testLine;
        }
    }
    if (currentLine.trim()) {
        lines.push(currentLine.trim());
    }
    
    // Center the text vertically with proper spacing
    const totalTextHeight = lines.length * lineHeight;
    const startY = (height - totalTextHeight) / 2 + 50; // Offset for title space
    
    // Add quotation marks with proper Chinese style
    ctx.fillStyle = '#1a1a1a';
    ctx.font = '90px serif';
    ctx.textAlign = 'left';
    ctx.fillText('「', 80, startY - 20); // Left Chinese quote mark
    
    // Draw text lines with left alignment and proper margins
    ctx.font = '42px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans CJK TC", sans-serif';
    ctx.fillStyle = '#2c2c2c';
    ctx.textAlign = 'left';
    
    lines.forEach((line, index) => {
        ctx.fillText(line, 80, startY + index * lineHeight); // 80px left margin
    });
    
    // Right quotation mark
    ctx.fillStyle = '#1a1a1a';
    ctx.font = '90px serif';
    ctx.textAlign = 'right';
    ctx.fillText('」', width - 80, startY + totalTextHeight - 20); // Right Chinese quote mark
    
    // Bottom attribution with better spacing
    ctx.textAlign = 'center';
    ctx.fillStyle = '#666';
    ctx.font = '38px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans CJK TC", sans-serif';
    ctx.fillText('— 股癌逐字稿', width / 2, height - 180);
    
    // Clean URL at bottom
    ctx.font = '30px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
    ctx.fillStyle = '#888';
    const shortUrl = 'whatmkreallysaid.com';
    ctx.fillText(shortUrl, width / 2, height - 120);
    
    // Convert canvas to blob
    return new Promise((resolve) => {
        canvas.toBlob(resolve, 'image/png', 0.9);
    });
}

// ────────────────────────────────────────────────────────────────────────
// Search-hit deep links: when user arrives via ?q=…&offset=… (clicked from
// the homepage search results), highlight every occurrence of the query in
// the rendered transcript and scroll to the most relevant one.
// ────────────────────────────────────────────────────────────────────────

function highlightSearchQuery(query, offsetParam) {
    if (!query) return;

    const body = document.querySelector('.episode-body');
    if (!body) return;

    const lowerQ = query.toLowerCase();
    const walker = document.createTreeWalker(body, NodeFilter.SHOW_TEXT, null);
    const textNodes = [];
    let node;
    while ((node = walker.nextNode())) textNodes.push(node);

    const marks = [];
    for (const tn of textNodes) {
        const text = tn.nodeValue;
        if (!text) continue;
        const lowerText = text.toLowerCase();
        let idx = lowerText.indexOf(lowerQ);
        if (idx < 0) continue;

        const frag = document.createDocumentFragment();
        let cursor = 0;
        while (idx >= 0) {
            if (idx > cursor) frag.appendChild(document.createTextNode(text.slice(cursor, idx)));
            const mark = document.createElement('mark');
            mark.className = 'search-hit';
            mark.textContent = text.slice(idx, idx + query.length);
            frag.appendChild(mark);
            marks.push(mark);
            cursor = idx + query.length;
            idx = lowerText.indexOf(lowerQ, cursor);
        }
        if (cursor < text.length) frag.appendChild(document.createTextNode(text.slice(cursor)));
        tn.parentNode.replaceChild(frag, tn);
    }

    if (marks.length === 0) return;

    // Decide which mark to scroll to. If the caller passed a markdown char
    // offset, pick the mark whose enclosing paragraph is closest to that
    // ratio of the document; otherwise use the first hit.
    let target = marks[0];
    const offset = Number.parseInt(offsetParam || '', 10);
    if (Number.isFinite(offset) && offset > 0) {
        const totalChars = (body.textContent || '').length;
        if (totalChars > 0) {
            const ratio = Math.min(1, offset / totalChars);
            const idx = Math.min(marks.length - 1, Math.floor(ratio * marks.length));
            target = marks[idx] || target;
        }
    }

    target.classList.add('search-hit-active');
    target.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

// Load episode on page load
document.addEventListener('DOMContentLoaded', () => {
    loadEpisode();
    setupDisclaimerToggle();
});