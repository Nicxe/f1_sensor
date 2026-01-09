#!/usr/bin/env node
/**
 * Comment on GitHub issues referenced via closing keywords in commit messages
 * included in the current semantic-release release.
 *
 * Supported keywords: fix|fixes|fixed|close|closes|closed|resolve|resolves|resolved
 * Supported references: #123 or owner/repo#123
 *
 * Intended to run from semantic-release via @semantic-release/exec successCmd.
 */
const { execSync } = require("node:child_process");

function getArg(flag) {
  const idx = process.argv.indexOf(flag);
  if (idx === -1) return undefined;
  return process.argv[idx + 1];
}

function sh(cmd) {
  return execSync(cmd, { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }).trim();
}

function parseRepo() {
  const fromEnv = process.env.GITHUB_REPOSITORY;
  if (fromEnv && /^[^/]+\/[^/]+$/.test(fromEnv)) return fromEnv;

  // Try reading origin remote url
  const url = sh("git config --get remote.origin.url");
  // Examples:
  // - git@github.com:owner/repo.git
  // - https://github.com/owner/repo.git
  const m =
    url.match(/github\.com[:/](.+?)\/(.+?)(?:\.git)?$/i) ||
    url.match(/github\.com\/(.+?)\/(.+?)(?:\.git)?$/i);
  if (!m) return undefined;
  return `${m[1]}/${m[2]}`;
}

function extractIssueRefs(text) {
  const refs = [];
  const re =
    /\b(?:close|closes|closed|fix|fixes|fixed|resolve|resolves|resolved)\s+((?:[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+)?#\d+)\b/gi;
  let match;
  while ((match = re.exec(text))) {
    refs.push(match[1]);
  }
  return refs;
}

function uniq(arr) {
  return [...new Set(arr)];
}

async function ghRequest(url, { method = "GET", token, body } = {}) {
  const headers = {
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28"
  };
  if (token) headers.Authorization = `token ${token}`;
  if (body) headers["Content-Type"] = "application/json";

  const res = await fetch(url, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined
  });
  const text = await res.text();
  const json = text ? JSON.parse(text) : null;
  if (!res.ok) {
    const msg = json?.message || text || `HTTP ${res.status}`;
    throw new Error(`${method} ${url} failed: ${msg}`);
  }
  return json;
}

async function main() {
  const token =
    process.env.GITHUB_TOKEN ||
    process.env.GH_TOKEN ||
    process.env.GITHUB_AUTH_TOKEN;

  if (!token) {
    console.log("[notify-issues] No GitHub token found; skipping.");
    return;
  }

  const repo = parseRepo();
  if (!repo) {
    console.log("[notify-issues] Could not determine GitHub repo; skipping.");
    return;
  }

  const range = getArg("--range");
  const version = getArg("--version");
  const gitTag = getArg("--git-tag"); // e.g. v1.2.3-beta.1
  const channel = getArg("--channel") || ""; // e.g. beta

  if (!range || range.includes("undefined") || !version) {
    console.log("[notify-issues] Missing/invalid range or version; skipping.");
    return;
  }

  const log = sh(`git log --format=%B ${range}`);
  const refs = uniq(extractIssueRefs(log));
  if (refs.length === 0) {
    console.log("[notify-issues] No issue references found; nothing to do.");
    return;
  }

  const [owner, name] = repo.split("/");
  const tagToShow = gitTag || `v${version}`;
  const isBeta = String(channel).toLowerCase() === "beta";
  const commentBody = isBeta
    ? `Included in beta release ${tagToShow}.`
    : `Included in release ${tagToShow}.`;

  const base = `https://api.github.com/repos/${owner}/${name}`;

  const issueNumbers = uniq(
    refs
      .map((r) => {
        // r is "#123" or "owner/repo#123"
        const m = r.match(/^(?:([^/]+)\/([^#]+))?#(\d+)$/);
        if (!m) return null;
        const refOwner = m[1];
        const refRepo = m[2];
        const num = m[3];
        // Only act on issues in this repo (avoid surprising cross-repo writes)
        if (refOwner && refRepo && `${refOwner}/${refRepo}` !== repo) return null;
        return num;
      })
      .filter(Boolean)
  );

  if (issueNumbers.length === 0) {
    console.log("[notify-issues] Only cross-repo references found; skipping.");
    return;
  }

  console.log(`[notify-issues] Commenting on issues: ${issueNumbers.join(", ")}`);

  for (const issueNumber of issueNumbers) {
    try {
      // Avoid duplicate comments if the job reruns
      const comments = await ghRequest(
        `${base}/issues/${issueNumber}/comments?per_page=50`,
        { token }
      );
      const already = Array.isArray(comments)
        ? comments.some((c) => typeof c?.body === "string" && c.body.includes(commentBody))
        : false;
      if (already) {
        console.log(`[notify-issues] #${issueNumber}: comment already present; skipping.`);
        continue;
      }

      await ghRequest(`${base}/issues/${issueNumber}/comments`, {
        method: "POST",
        token,
        body: { body: commentBody }
      });
      console.log(`[notify-issues] #${issueNumber}: commented.`);
    } catch (e) {
      console.log(`[notify-issues] #${issueNumber}: failed: ${e.message}`);
    }
  }
}

main().catch((e) => {
  console.error(`[notify-issues] Fatal: ${e.message}`);
  process.exitCode = 0; // don't fail the release because of notifications
});

