'use strict';
const {extractField, versionState, componentLabels, releaseIssues} = require('./issue-fields.cjs');
const releaseComment = require('./release-comment.cjs');

async function ensureLabel(github, repo, name, color) {
  try { await github.rest.issues.getLabel({...repo, name}); }
  catch (error) {
    if (error.status !== 404) throw error;
    try { await github.rest.issues.createLabel({...repo, name, color}); }
    catch (createError) {
      if (createError.status !== 422) throw createError;
      await github.rest.issues.getLabel({...repo, name});
    }
  }
}

async function removeLabel(github, issue, name) {
  try { await github.rest.issues.removeLabel({...issue, name}); }
  catch (error) { if (error.status !== 404) throw error; }
}

async function upsertComment(github, issue, marker, body, legacyMatch = () => false, onlyExisting = false) {
  const comments = await github.paginate(github.rest.issues.listComments, {...issue, per_page:100});
  const existing = comments.find(c => c.user?.login === 'github-actions[bot]' && (c.body?.includes(marker) || legacyMatch(c.body || '')));
  const complete = `${marker}\n${body}`;
  if (!existing && !onlyExisting) await github.rest.issues.createComment({...issue, body:complete});
  else if (existing && existing.body !== complete && !legacyMatch(existing.body || '')) {
    await github.rest.issues.updateComment({...issue, comment_id:existing.id, body:complete});
  }
}

async function updateIssue({github, context}, mode) {
  const key = {...context.repo, issue_number:context.payload.issue.number};
  const {data:issue} = await github.rest.issues.get(key);
  if (issue.pull_request) return;
  const labels = issue.labels.map(l => l.name || l);
  if (mode === 'component') {
    const desired = componentLabels(issue.body);
    for (const name of desired) await ensureLabel(github, context.repo, name, 'bfd4f2');
    if (desired.length) await github.rest.issues.addLabels({...key, labels:desired});
    // Only component labels managed by this workflow are reconciled.
    for (const name of ['integration','card','blueprint','documentation']) {
      if (labels.includes(name) && !desired.includes(name)) await removeLabel(github, key, name);
    }
    return;
  }
  if (!labels.includes('bug')) return;
  const reported = extractField(issue.body, 'F1 Sensor Version');
  let latest = '';
  try { latest = (await github.rest.repos.getLatestRelease(context.repo)).data.tag_name; }
  catch (error) { if (error.status !== 404) throw error; }
  const state = versionState(reported, latest);
  for (const name of ['beta','outdated-version']) {
    if (labels.includes(name) && name !== state) await removeLabel(github, key, name);
  }
  if (!['beta','outdated-version'].includes(state)) {
    await upsertComment(github, key, '<!-- f1-version-check -->', 'The reported version has changed. This issue is no longer marked as using an older stable release or a beta; no automatic closure is scheduled.', () => false, true);
    return;
  }
  await ensureLabel(github, context.repo, state, state === 'beta' ? 'bfd4f2' : 'e4e669');
  await github.rest.issues.addLabels({...key, labels:[state]});
  const restart = componentLabels(issue.body).includes('card') ? 'Restart Home Assistant, then reload your browser so the dashboard loads fresh card assets.' : 'Restart Home Assistant.';
  const body = state === 'beta'
    ? `Thanks for testing the beta and taking the time to report this!\n\nYou're running **F1 Sensor ${reported}**, a pre-release version. Beta feedback helps improve F1 Sensor before stable releases.\n\nIf this affects your day-to-day use, you can return to the latest stable release: open **HACS → Integrations → F1 Sensor**, select **Redownload**, and choose the stable version. ${restart}\n\nWe'll look into this — thanks again for helping test!`
    : `Thanks for the report!\n\nYou're running **${reported}**; the latest stable release is **${latest}**. Please update and check whether the issue still occurs.\n\nOpen **HACS → Integrations → F1 Sensor** and select **Update** (or **Redownload** to choose a version). ${restart}\n\nIf the issue persists after updating, please comment here and we'll continue investigating.`;
  await upsertComment(github, key, '<!-- f1-version-check -->', body);
}

async function releasedIssues({github, context}) {
  const release = context.payload.release;
  if (!release || release.draft) return;
  const numbers = releaseIssues(release.body, `${context.repo.owner}/${context.repo.repo}`);
  for (const number of numbers) {
    const key = {...context.repo, issue_number:number};
    let issue;
    try { issue = (await github.rest.issues.get(key)).data; }
    catch (error) { if (error.status === 404) continue; throw error; }
    if (issue.pull_request) continue;
    if (release.prerelease && issue.state !== 'closed') {
      await ensureLabel(github, context.repo, 'In BETA-testing', 'fbca04');
      await github.rest.issues.addLabels({...key, labels:['In BETA-testing']});
    } else if (!release.prerelease && issue.labels.some(l => (l.name || l) === 'In BETA-testing')) {
      await removeLabel(github, key, 'In BETA-testing');
    }
    await upsertComment(github, key, `<!-- f1-release:${release.id} -->`, releaseComment(issue, release), body => body.includes(release.html_url) && /A fix for this issue is now available|This feature has been implemented|This feature is now available/.test(body));
  }
}

module.exports = {ensureLabel, removeLabel, upsertComment, updateIssue, releasedIssues};
