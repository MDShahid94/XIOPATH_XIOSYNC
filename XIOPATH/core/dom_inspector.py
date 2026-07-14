import json
from typing import Dict, Any, List

class DOMInspector:
    """
    Deep Data Analysis module for the custom agent.
    Extracts the DOM tree, identifies interactive elements, and calculates bounding boxes.
    Provides a compressed representation for the LLM.
    """
    def __init__(self, page):
        self.page = page

    async def get_interactive_elements(self) -> (str, Dict[int, Any]):
        """
        Injects JS into the page to extract all interactive elements, their bounding boxes,
        and generates a token-efficient map for the LLM.
        Returns:
            - string representation for the prompt.
            - dict mapping node_id to playwright selector/coordinates.
        """
        js_script = """
        () => {
            // ━━━ SECURITY: XPath/CSS Injection Prevention ━━━━━━━━━━━━━━━━━━
            function escapeXPathString(str) {
                if (!str) return '""';
                if (!str.includes('"')) return '"' + str + '"';
                if (!str.includes("'")) return "'" + str + "'";
                // Contains both quote types — use XPath concat()
                return "concat(" + str.split('"').map(s => '"' + s + '"').join(",'\"',") + ")";
            }

            function escapeCssId(id) {
                if (!id) return '';
                return id.replace(/([\\\\!\"#$%&'()*+,./:;<=>?@[\\]^`{|}~])/g, '\\\\$1');
            }

            // ━━━ VISIBILITY: Enterprise-Grade Element Visibility Check ━━━━━
            function isElementTrulyVisible(el) {
                const rect = el.getBoundingClientRect();
                if (rect.width <= 0 || rect.height <= 0) return false;

                const cs = window.getComputedStyle(el);
                if (cs.display === 'none') return false;
                if (cs.visibility === 'hidden') return false;
                if (parseFloat(cs.opacity) === 0) return false;
                if (el.getAttribute('aria-hidden') === 'true') return false;

                // Check ancestors for hidden containers (depth-limited)
                let parent = el.parentElement;
                let depth = 0;
                while (parent && depth < 15) {
                    const pcs = window.getComputedStyle(parent);
                    if (pcs.display === 'none' || pcs.visibility === 'hidden' || parseFloat(pcs.opacity) === 0) return false;
                    parent = parent.parentElement;
                    depth++;
                }
                return true;
            }

            // ━━━ SHADOW DOM: Recursive element discovery ━━━━━━━━━━━━━━━━━━
            function deepQuerySelectorAll(root, selector) {
                let results = Array.from(root.querySelectorAll(selector));
                // Penetrate shadow roots
                const allElements = root.querySelectorAll('*');
                for (const el of allElements) {
                    if (el.shadowRoot) {
                        results = results.concat(deepQuerySelectorAll(el.shadowRoot, selector));
                    }
                }
                return results;
            }

            // ━━━ LOCATOR GENERATORS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            function getCssSelector(el) {
                if (el.id) return '#' + escapeCssId(el.id);
                let path = [];
                let current = el;
                while (current && current.nodeType === Node.ELEMENT_NODE) {
                    let selector = current.nodeName.toLowerCase();
                    if (current.id) {
                        selector += '#' + escapeCssId(current.id);
                        path.unshift(selector);
                        break;
                    }
                    let sibling = current, nth = 1;
                    while (sibling = sibling.previousElementSibling) {
                        if (sibling.nodeName.toLowerCase() === selector) nth++;
                    }
                    if (nth != 1) selector += ":nth-of-type("+nth+")";
                    path.unshift(selector);
                    current = current.parentNode;
                }
                return path.join(" > ");
            }
            
            function getXPath(el) {
                if (el.id) return '//*[@id=' + escapeXPathString(el.id) + ']';
                let parts = [];
                while (el && el.nodeType === Node.ELEMENT_NODE) {
                    let sibling = el.previousSibling;
                    let count = 1;
                    while (sibling) {
                        if (sibling.nodeType === Node.ELEMENT_NODE && sibling.nodeName === el.nodeName) count++;
                        sibling = sibling.previousSibling;
                    }
                    let part = el.nodeName.toLowerCase() + (count > 1 ? '[' + count + ']' : '[1]');
                    parts.unshift(part);
                    el = el.parentNode;
                }
                return parts.length ? '/' + parts.join('/') : null;
            }

            // ━━━ AXES XPATH: Uniqueness-Validated Relational Locators ━━━━━
            function countXPathMatches(xpath) {
                try {
                    const xr = document.evaluate(xpath, document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
                    return xr.snapshotLength;
                } catch { return 0; }
            }

            function getAxesXPath(el) {
                const axes = [];
                const elTag = el.tagName.toLowerCase();
                const MAX_ANCESTOR_DEPTH = 20;

                // Strategy 1: Ancestor-anchored — find nearest ancestor with stable identifier
                let ancestor = el.parentNode;
                let depth = 0;
                while (ancestor && ancestor !== document.body && ancestor !== document && depth < MAX_ANCESTOR_DEPTH) {
                    depth++;
                    let anchorAttr = null;
                    let anchorVal = null;
                    let strategy = null;
                    let baseStability = 0;

                    if (ancestor.id) {
                        anchorAttr = 'id';
                        anchorVal = ancestor.id;
                        strategy = 'ancestor_id';
                        baseStability = 0.95;
                    } else if (ancestor.getAttribute && ancestor.getAttribute('data-testid')) {
                        anchorAttr = 'data-testid';
                        anchorVal = ancestor.getAttribute('data-testid');
                        strategy = 'ancestor_testid';
                        baseStability = 0.92;
                    }

                    if (anchorAttr) {
                        // Build discriminating XPath — try to narrow beyond just tag
                        let xpath = '//*[@' + anchorAttr + '=' + escapeXPathString(anchorVal) + ']//' + elTag;
                        let matchCount = countXPathMatches(xpath);

                        // If ambiguous, add discriminating attributes
                        if (matchCount > 1) {
                            const elName = el.getAttribute('name');
                            const elType = el.getAttribute('type');
                            const elPlaceholder = el.getAttribute('placeholder');
                            if (elName) {
                                xpath += '[@name=' + escapeXPathString(elName) + ']';
                            } else if (elType) {
                                xpath += '[@type=' + escapeXPathString(elType) + ']';
                            } else if (elPlaceholder) {
                                xpath += '[contains(@placeholder,' + escapeXPathString(elPlaceholder.substring(0, 40)) + ')]';
                            } else {
                                // Use positional index within ancestor
                                const siblings = ancestor.querySelectorAll(elTag);
                                let pos = 0;
                                for (let i = 0; i < siblings.length; i++) {
                                    if (siblings[i] === el) { pos = i + 1; break; }
                                }
                                if (pos > 0) xpath = '//*[@' + anchorAttr + '=' + escapeXPathString(anchorVal) + ']//' + elTag + '[' + pos + ']';
                            }
                            matchCount = countXPathMatches(xpath);
                        }

                        axes.push({
                            strategy: strategy,
                            xpath: xpath,
                            stability: matchCount === 1 ? baseStability : baseStability * 0.6,
                            unique: matchCount === 1,
                        });
                        break;
                    }
                    ancestor = ancestor.parentNode;
                }

                // Strategy 2: Sibling-anchored — preceding label, heading, or text element
                let prevSibling = el.previousElementSibling;
                let sibDepth = 0;
                while (prevSibling && sibDepth < 5) {
                    sibDepth++;
                    const sibText = prevSibling.innerText ? prevSibling.innerText.trim() : '';
                    if (sibText.length > 0 && sibText.length <= 60) {
                        const sibTag = prevSibling.tagName.toLowerCase();
                        const xpath = '//' + sibTag + '[normalize-space()=' + escapeXPathString(sibText) + ']/following-sibling::' + elTag + '[1]';
                        const matchCount = countXPathMatches(xpath);
                        axes.push({
                            strategy: "sibling_text",
                            xpath: xpath,
                            stability: matchCount === 1 ? 0.85 : 0.50,
                            unique: matchCount === 1,
                        });
                        break;
                    }
                    prevSibling = prevSibling.previousElementSibling;
                }

                // Strategy 3: Parent-label association (<label for="...">)
                if (el.id) {
                    const labelFor = document.querySelector('label[for=' + JSON.stringify(el.id) + ']');
                    if (labelFor && labelFor.innerText) {
                        const xpath = '//label[normalize-space()=' + escapeXPathString(labelFor.innerText.trim()) + ']/following::' + elTag + '[1]';
                        const matchCount = countXPathMatches(xpath);
                        axes.push({
                            strategy: "label_for",
                            xpath: xpath,
                            stability: matchCount === 1 ? 0.90 : 0.55,
                            unique: matchCount === 1,
                        });
                    }
                }

                // Strategy 4: Semantic-anchored — use element's own meaningful attributes
                const ariaLabel = el.getAttribute('aria-label');
                const placeholder = el.getAttribute('placeholder');
                const name = el.getAttribute('name');
                if (ariaLabel) {
                    const xpath = '//' + elTag + '[@aria-label=' + escapeXPathString(ariaLabel) + ']';
                    const matchCount = countXPathMatches(xpath);
                    axes.push({
                        strategy: "semantic_aria",
                        xpath: xpath,
                        stability: matchCount === 1 ? 0.88 : 0.52,
                        unique: matchCount === 1,
                    });
                } else if (placeholder) {
                    const xpath = '//' + elTag + '[contains(@placeholder,' + escapeXPathString(placeholder.substring(0, 40)) + ')]';
                    const matchCount = countXPathMatches(xpath);
                    axes.push({
                        strategy: "semantic_placeholder",
                        xpath: xpath,
                        stability: matchCount === 1 ? 0.80 : 0.48,
                        unique: matchCount === 1,
                    });
                } else if (name) {
                    const xpath = '//' + elTag + '[@name=' + escapeXPathString(name) + ']';
                    const matchCount = countXPathMatches(xpath);
                    axes.push({
                        strategy: "semantic_name",
                        xpath: xpath,
                        stability: matchCount === 1 ? 0.85 : 0.50,
                        unique: matchCount === 1,
                    });
                }

                // Sort by stability (highest first), return top 3
                axes.sort((a, b) => b.stability - a.stability);
                return axes.slice(0, 3);
            }

            // ━━━ EXTENDED TEST-ID COVERAGE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            function getTestId(el) {
                return el.getAttribute('data-testid')
                    || el.getAttribute('data-test-id')
                    || el.getAttribute('data-test')
                    || el.getAttribute('data-cy')
                    || el.getAttribute('data-automation-id')
                    || el.getAttribute('data-qa')
                    || null;
            }
            
            function getAriaName(el) {
                let name = el.getAttribute('aria-label') || el.getAttribute('name') || el.title || el.innerText || '';
                return name.trim().substring(0, 50);
            }
            
            function getAnchorText(el) {
                let sibling = el.previousElementSibling;
                let depth = 0;
                while (sibling && depth < 5) {
                    if (sibling.innerText && sibling.innerText.trim() !== '') return sibling.innerText.trim().substring(0, 50);
                    sibling = sibling.previousElementSibling;
                    depth++;
                }
                return null;
            }

            function getElementSignature(el) {
                const cs = window.getComputedStyle(el);
                return {
                    tag: el.tagName.toLowerCase(),
                    classes: (el.className && typeof el.className === 'string') ? el.className.trim().split(/\\s+/).slice(0, 5) : [],
                    computed_color: cs.color,
                    computed_font_size: cs.fontSize,
                    computed_bg: cs.backgroundColor,
                };
            }

            // ━━━ MAIN EXTRACTION ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            const interactiveSelectors = 'a, button, input, select, textarea, [role="button"], [role="link"], [role="tab"], [role="menuitem"], [role="checkbox"], [role="radio"], [tabindex]:not([tabindex="-1"])';
            const elements = deepQuerySelectorAll(document, interactiveSelectors);
            let nodes = [];
            let idCounter = 1;
            
            elements.forEach(el => {
                // Enterprise visibility check (replaces simple rect check)
                if (!isElementTrulyVisible(el)) return;
                const rect = el.getBoundingClientRect();
                
                let text = getAriaName(el);
                
                if (text !== '' || el.tagName.toLowerCase() === 'input' || el.tagName.toLowerCase() === 'select') {
                    if (text === '') text = 'empty input';
                    nodes.push({
                        node_id: idCounter++,
                        tag: el.tagName.toLowerCase(),
                        text: text,
                        inner_text: el.innerText ? el.innerText.trim() : '',
                        selector: getCssSelector(el),
                        xpath: getXPath(el),
                        axes_xpath: getAxesXPath(el),
                        test_id: getTestId(el),
                        aria_name: text,
                        role: el.getAttribute('role') || el.tagName.toLowerCase(),
                        anchor_text: getAnchorText(el),
                        x: Math.round(rect.x + rect.width / 2),
                        y: Math.round(rect.y + rect.height / 2),
                        width: Math.round(rect.width),
                        height: Math.round(rect.height),
                        bounding_box: {
                            x: Math.round(rect.x),
                            y: Math.round(rect.y),
                            width: Math.round(rect.width),
                            height: Math.round(rect.height),
                            nx: rect.x / window.innerWidth,
                            ny: rect.y / window.innerHeight,
                            nw: rect.width / window.innerWidth,
                            nh: rect.height / window.innerHeight,
                            windowWidth: window.innerWidth,
                            windowHeight: window.innerHeight,
                            scrollX: window.scrollX,
                            scrollY: window.scrollY,
                        },
                        element_signature: getElementSignature(el),
                    });
                    el.setAttribute('data-ag-node-id', idCounter - 1);
                }
            });
            return nodes;
        }
        """
        
        nodes_data = await self.page.evaluate(js_script)
        
        node_map = {}
        dom_string_lines = ["Interactive Elements Map:"]
        
        for node in nodes_data:
            nid = node['node_id']
            node_map[str(nid)] = node  # E-04: Always string keys for consistent lookup
            dom_string_lines.append(f"[{nid}] <{node['tag']}> \"{node['text']}\"")
            
        dom_string = "\\n".join(dom_string_lines)
        return dom_string, node_map

    async def get_page_text(self) -> str:
        """Gets a clean text representation of the page content."""
        js_script = "() => document.body.innerText;"
        text = await self.page.evaluate(js_script)
        # basic cleanup
        lines = [line.strip() for line in text.split('\\n') if line.strip()]
        return "\\n".join(lines)
