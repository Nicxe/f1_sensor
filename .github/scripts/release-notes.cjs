'use strict';

const {execFileSync} = require('node:child_process');
const {latestStableTag, mergedReleaseTags, parseReleaseTag} = require('./release-stage.cjs');

function commitsBetween(from, to, context) {
  const run = args => execFileSync('git', args, {
    cwd: context.cwd, env: context.env, encoding: 'utf8'
  }).trim();
  return run(['rev-list', from ? `${from}..${to}` : to])
    .split('\n').filter(Boolean).map(hash => ({
      hash,
      message: run(['show', '-s', '--format=%B', hash]),
      committerDate: run(['show', '-s', '--format=%cI', hash])
    }));
}

async function generateNotes(pluginConfig, context) {
  const tag = context.nextRelease.gitTag;
  const release = parseReleaseTag(tag);
  let notesContext = context;
  if (release?.stage === 'rc') {
    const head = context.nextRelease.gitHead || 'HEAD';
    const previous = latestStableTag(mergedReleaseTags(head, context));
    notesContext = {
      ...context,
      commits: commitsBetween(previous, head, context),
      lastRelease: previous ? {gitTag: previous, gitHead: previous, version: previous.slice(1)} : {}
    };
  }
  const {generateNotes: render} = await import('@semantic-release/release-notes-generator');
  // Each render gets fresh filtering/deduplication state from the shared config.
  const options = pluginConfig.createOptions();
  const finalizeContext = options.writerOpts.finalizeContext;
  options.writerOpts.finalizeContext = (...args) => {
    const finalized = finalizeContext(...args);
    finalized.releaseCandidate = release?.stage === 'rc';
    return finalized;
  };
  return render(options, notesContext);
}

module.exports = {commitsBetween, generateNotes};
