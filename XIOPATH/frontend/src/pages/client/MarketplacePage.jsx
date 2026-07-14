/**
 * XIOPATH — Marketplace Page (Phase F.3)
 * ========================================
 * Browse, search, and install workflow environments from the marketplace.
 * Premium dark UI with card grid, category filters, and search.
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  Search, Package, Download, Star, Filter, ChevronRight,
  Sparkles, ShoppingBag, TrendingUp, Tag, ArrowRight, X, Store,
} from 'lucide-react';
import useMarketplaceStore from '../../stores/marketplaceStore';
import useToastStore from '../../stores/toastStore';

const CATEGORIES = [
  { id: '', label: 'All', icon: Sparkles },
  { id: 'automation', label: 'Automation', icon: Package },
  { id: 'scraping', label: 'Scraping', icon: Search },
  { id: 'testing', label: 'Testing', icon: ShoppingBag },
  { id: 'data-extraction', label: 'Data', icon: TrendingUp },
  { id: 'utility', label: 'Utility', icon: Tag },
];

function MarketplaceCard({ listing, onInstall, onViewDetail }) {
  const tags = Array.isArray(listing.tags) ? listing.tags : [];
  const rating = listing.rating || 0;
  const installs = listing.install_count || 0;

  return (
    <div className="mp-card" onClick={() => onViewDetail(listing)}>
      <div className="mp-card-header">
        <div className="mp-card-icon">
          <Package size={22} />
        </div>
        <div className="mp-card-category">{listing.category || 'automation'}</div>
      </div>

      <h3 className="mp-card-title">{listing.title}</h3>
      <p className="mp-card-desc">{listing.description || 'No description available.'}</p>

      {tags.length > 0 && (
        <div className="mp-card-tags">
          {tags.slice(0, 3).map((tag) => (
            <span key={tag} className="mp-tag">{tag}</span>
          ))}
        </div>
      )}

      <div className="mp-card-footer">
        <div className="mp-card-stats">
          <span className="mp-stat">
            <Download size={13} /> {installs}
          </span>
          <span className="mp-stat">
            <Star size={13} fill={rating > 0 ? 'var(--xp-warning)' : 'none'} /> {rating.toFixed(1)}
          </span>
        </div>
        <button
          className="mp-install-btn"
          onClick={(e) => { e.stopPropagation(); onInstall(listing.id); }}
        >
          Install <ArrowRight size={14} />
        </button>
      </div>
    </div>
  );
}

function DetailModal({ listing, onClose, onInstall, onReview }) {
  const [rating, setRating] = useState(5);
  const [comment, setComment] = useState('');

  if (!listing) return null;

  const tags = Array.isArray(listing.tags) ? listing.tags : [];
  const reviews = listing.reviews || [];

  return (
    <div className="mp-modal-overlay" onClick={onClose}>
      <div className="mp-modal" onClick={(e) => e.stopPropagation()}>
        <button className="mp-modal-close" onClick={onClose}><X size={18} /></button>

        <div className="mp-modal-header">
          <div className="mp-card-icon" style={{ width: 56, height: 56, fontSize: 24 }}>
            <Package size={28} />
          </div>
          <div>
            <h2 className="mp-modal-title">{listing.title}</h2>
            <div className="mp-modal-meta">
              <span>{listing.category}</span>
              <span>•</span>
              <span>{listing.install_count || 0} installs</span>
              <span>•</span>
              <span><Star size={12} fill="var(--xp-warning)" /> {(listing.rating || 0).toFixed(1)}</span>
            </div>
          </div>
        </div>

        <p className="mp-modal-desc">{listing.description || 'No description.'}</p>

        {tags.length > 0 && (
          <div className="mp-card-tags" style={{ marginBottom: 20 }}>
            {tags.map((t) => <span key={t} className="mp-tag">{t}</span>)}
          </div>
        )}

        <button
          className="mp-install-btn mp-install-full"
          onClick={() => onInstall(listing.id)}
        >
          <Download size={16} /> Install Environment
        </button>

        {/* Reviews Section */}
        <div className="mp-reviews-section">
          <h3>Reviews ({reviews.length})</h3>
          {reviews.length === 0 && <p className="mp-no-reviews">No reviews yet.</p>}
          {reviews.map((r) => (
            <div key={r.id} className="mp-review">
              <div className="mp-review-header">
                <span className="mp-review-stars">
                  {Array.from({ length: 5 }).map((_, i) => (
                    <Star key={i} size={12} fill={i < r.rating ? 'var(--xp-warning)' : 'none'} stroke="var(--xp-warning)" />
                  ))}
                </span>
                <span className="mp-review-author">{r.reviewer_id?.slice(0, 8)}...</span>
              </div>
              {r.comment && <p className="mp-review-text">{r.comment}</p>}
            </div>
          ))}

          {/* Add Review */}
          <div className="mp-add-review">
            <h4>Leave a Review</h4>
            <div className="mp-rating-input">
              {Array.from({ length: 5 }).map((_, i) => (
                <Star
                  key={i}
                  size={20}
                  fill={i < rating ? 'var(--xp-warning)' : 'none'}
                  stroke="var(--xp-warning)"
                  style={{ cursor: 'pointer' }}
                  onClick={() => setRating(i + 1)}
                />
              ))}
            </div>
            <textarea
              className="mp-review-input"
              placeholder="Write a comment..."
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              rows={2}
            />
            <button
              className="mp-install-btn"
              style={{ marginTop: 8 }}
              onClick={() => { onReview(listing.id, rating, comment); setComment(''); }}
            >
              Submit Review
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function MarketplacePage() {
  const {
    listings, loading, error, total, query,
    browse, search, clearSearch, install, review, getDetail, currentListing,
  } = useMarketplaceStore();

  const [selectedCategory, setSelectedCategory] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [showDetail, setShowDetail] = useState(false);
  const addToast = useToastStore((s) => s.addToast);

  useEffect(() => {
    browse();
  }, [browse]);

  const handleCategoryClick = useCallback((catId) => {
    setSelectedCategory(catId);
    clearSearch();
    setSearchInput('');
    browse(catId);
  }, [browse, clearSearch]);

  const handleSearch = useCallback((e) => {
    e.preventDefault();
    if (searchInput.trim()) {
      search(searchInput.trim());
    } else {
      clearSearch();
      browse(selectedCategory);
    }
  }, [searchInput, selectedCategory, search, clearSearch, browse]);

  const handleInstall = useCallback(async (listingId) => {
    try {
      const result = await install(listingId);
      addToast(`Installed "${result.title}" successfully!`, 'success');
    } catch {
      addToast('Install failed. Please try again.', 'error');
    }
  }, [install, addToast]);

  const handleViewDetail = useCallback(async (listing) => {
    await getDetail(listing.id);
    setShowDetail(true);
  }, [getDetail]);

  const displayList = query ? useMarketplaceStore.getState().searchResults : listings;

  return (
    <div className="mp-page xp-animate-fade-in">
      {/* Header */}
      <div className="mp-header">
        <div className="mp-header-text">
          <h1 className="mp-title">
            <Store size={28} /> Marketplace
          </h1>
          <p className="mp-subtitle">
            Discover and install pre-built workflow environments
          </p>
        </div>

        {/* Search */}
        <form className="mp-search" onSubmit={handleSearch}>
          <Search size={16} className="mp-search-icon" />
          <input
            type="text"
            placeholder="Search workflows, automations..."
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            className="mp-search-input"
          />
          {searchInput && (
            <button type="button" className="mp-search-clear" onClick={() => {
              setSearchInput('');
              clearSearch();
              browse(selectedCategory);
            }}>
              <X size={14} />
            </button>
          )}
        </form>
      </div>

      {/* Categories */}
      <div className="mp-categories">
        {CATEGORIES.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            className={`mp-category-btn ${selectedCategory === id ? 'active' : ''}`}
            onClick={() => handleCategoryClick(id)}
          >
            <Icon size={14} /> {label}
          </button>
        ))}
      </div>

      {/* Error */}
      {error && (
        <div className="xp-alert xp-alert-error" style={{ margin: '0 0 16px' }}>
          {error}
        </div>
      )}

      {/* Grid */}
      {loading ? (
        <div className="mp-loading">
          <div className="xp-animate-spin" style={{
            width: 28, height: 28, border: '2px solid var(--xp-border-subtle)',
            borderTop: '2px solid var(--xp-cyan)', borderRadius: '50%',
          }} />
          <span>Loading marketplace...</span>
        </div>
      ) : displayList.length === 0 ? (
        <div className="mp-empty">
          <Package size={48} strokeWidth={1} />
          <h3>No environments found</h3>
          <p>{query ? `No results for "${query}"` : 'The marketplace is empty. Publish your first environment!'}</p>
        </div>
      ) : (
        <>
          <div className="mp-grid">
            {displayList.map((listing) => (
              <MarketplaceCard
                key={listing.id}
                listing={listing}
                onInstall={handleInstall}
                onViewDetail={handleViewDetail}
              />
            ))}
          </div>
          {!query && total > displayList.length && (
            <div className="mp-load-more">
              <button
                className="mp-category-btn"
                onClick={() => browse(selectedCategory, displayList.length)}
              >
                Load More <ChevronRight size={14} />
              </button>
            </div>
          )}
        </>
      )}

      {/* Detail Modal */}
      {showDetail && (
        <DetailModal
          listing={currentListing}
          onClose={() => setShowDetail(false)}
          onInstall={handleInstall}
          onReview={review}
        />
      )}
    </div>
  );
}
