"use client";

import React, { useState } from "react";
import { Container } from "../../components/Container";
import { Button } from "../../components/Button";
import { PostCard } from "../../components/posts/PostCard";
import type { PublicPostResponse } from "../../lib/api-client";
import { searchPosts } from "../../lib/api-client";
import { translate } from "../../lib/i18n";

export interface SearchPageProps {
  initialResults?: PublicPostResponse[];
}

export default function SearchPage({ initialResults }: SearchPageProps) {
  const [query, setQuery] = useState<string>("");
  const [language, setLanguage] = useState<string>("");
  const [results, setResults] = useState<PublicPostResponse[]>(
    initialResults ?? []
  );

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim().length < 2) return;
    const res = await searchPosts({
      q: query.trim(),
      lang: language || undefined,
    });
    if (res.ok) {
      setResults(res.data.items);
    }
  };

  return (
    <Container className="max-w-4xl space-y-8">
      <h1 className="text-2xl font-bold text-slate-900 dark:text-white">
        {translate("search.pageTitle")}
      </h1>

      <form
        onSubmit={(e) => void handleSearch(e)}
        className="flex flex-col gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:flex-row dark:border-slate-800 dark:bg-slate-900"
      >
        <label htmlFor="search-q-input" className="sr-only">
          {translate("search.queryPlaceholder")}
        </label>
        <input
          id="search-q-input"
          type="search"
          required
          minLength={2}
          placeholder={translate("search.queryPlaceholder")}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
        />

        <select
          aria-label={translate("feed.filterLanguageLabel")}
          value={language}
          onChange={(e) => setLanguage(e.target.value)}
          className="rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
        >
          <option value="">{translate("feed.allLanguages")}</option>
          <option value="en">English (en)</option>
          <option value="ml">Malayalam — മലയാളം (ml)</option>
          <option value="hi">Hindi — हिन्दी (hi)</option>
          <option value="ta">Tamil — தமிழ் (ta)</option>
          <option value="mul">Mixed / Code-Switched (mul)</option>
        </select>

        <Button type="submit">{translate("search.searchButton")}</Button>
      </form>

      {results.length === 0 ? (
        <div className="rounded-xl border border-slate-200 bg-white p-8 text-center text-sm text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">
          {translate("search.noResults")}
        </div>
      ) : (
        <div className="space-y-4">
          {results.map((p) => (
            <PostCard key={p.id} post={p} />
          ))}
        </div>
      )}
    </Container>
  );
}
