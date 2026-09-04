'use strict';

function extractField(body, label) {
  const sections = String(body || '').replace(/\r\n/g, '\n').split(/^###\s+/m);
  for (const section of sections) {
    const newline = section.indexOf('\n');
    if (section.slice(0, newline).trim().toLowerCase() !== label.toLowerCase()) continue;
    const value = section.slice(newline + 1).trim();
    return /^_?no response_?$/i.test(value) ? '' : value;
  }
  return '';
}

function parseVersion(value) {
  const match = String(value).trim().match(/^v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$/);
  return match ? {numbers: match.slice(1, 4).map(Number), prerelease: match[4] || ''} : null;
}

function versionState(reported, latest) {
  const a = parseVersion(reported), b = parseVersion(latest);
  if (!a) return 'unknown';
  if (a.prerelease) return /(?:^|[.-])beta(?:[.-]|$)/i.test(a.prerelease) ? 'beta' : 'unknown';
  if (!b || b.prerelease) return 'unknown';
  for (let i = 0; i < 3; i++) {
    if (a.numbers[i] < b.numbers[i]) return 'outdated-version';
    if (a.numbers[i] > b.numbers[i]) return 'newer';
  }
  return 'current';
}

function componentLabels(body) {
  const value = extractField(body, 'Component').toLowerCase();
  return [
    ['integration', value.includes('integration')],
    ['card', value.includes('card')],
    ['blueprint', value.includes('blueprint')],
    ['documentation', value.includes('documentation') || value.includes('docs')],
  ].filter(([, enabled]) => enabled).map(([name]) => name);
}

function releaseIssues(body, repository) {
  const result = new Set();
  // Consume the whole Markdown link so a foreign #number in its label cannot
  // accidentally refer to an unrelated issue in this repository.
  let text = String(body || '').replace(/\[[^\]]*\]\((https?:\/\/[^\s)]+)\)/g, (_all, url) => {
    const match = url.match(/^https:\/\/github\.com\/([^/]+\/[^/]+)\/issues\/(\d+)(?:[/?#]|$)/i);
    if (match && match[1].toLowerCase() === repository.toLowerCase()) result.add(Number(match[2]));
    return '';
  });
  text = text.replace(/https:\/\/github\.com\/([^\s/]+\/[^\s/]+)\/(issues|pull)\/(\d+)[^\s)]*/g, (_all, repo, kind, number) => {
    if (repo.toLowerCase() === repository.toLowerCase() && kind === 'issues') result.add(Number(number));
    return '';
  });
  text = text.replace(/\b([\w.-]+\/[\w.-]+)#(\d+)/g, (_all, repo, number) => {
    if (repo.toLowerCase() === repository.toLowerCase()) result.add(Number(number));
    return '';
  }).replace(/https?:\/\/[^\s)]+/g, '');
  for (const match of text.matchAll(/(?<![\w/#])#(\d+)\b/g)) result.add(Number(match[1]));
  return [...result];
}

module.exports = {extractField, parseVersion, versionState, componentLabels, releaseIssues};
