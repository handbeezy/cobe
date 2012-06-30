# Copyright (C) 2012 Peter Teichman

import os
import random
import shutil
import unittest

from cobe.model import Model, TokenRegistry


TEST_MODEL = "test_model.cobe"


class TestTokenRegistry(unittest.TestCase):
    def test_get_new_tokens(self):
        tokens = TokenRegistry()

        # First, register four new tokens and make sure they get the
        # expected ids.
        for token_id, token in enumerate("this is a test".split()):
            self.assertEquals(chr(token_id), tokens.get_id(token))

        # Then, repeat the same check to make sure they aren't
        # re-registered.
        for token_id, token in enumerate("this is a test".split()):
            self.assertEquals(chr(token_id), tokens.get_id(token))


class TestModel(unittest.TestCase):
    def setUp(self):
        if os.path.exists(TEST_MODEL):
            shutil.rmtree(TEST_MODEL)

    def test_init(self):
        self.assertFalse(os.path.exists(TEST_MODEL))

        # Don't specify any ngram orders, which should get trigrams,
        # bigrams, and unigrams stored.
        model = Model(TEST_MODEL)

        self.assertTrue(os.path.exists(TEST_MODEL))
        self.assertEquals((3, 2, 1), model.orders)

    def test_load_tokens(self):
        # Ensure that model.tokens is properly reloaded from the
        # database when an old Model is loaded
        model = Model(TEST_MODEL)

        model.train("this is a test".split())
        model.train("this is another test".split())

        # We save on train(), so make sure the new tokens log is empty.
        self.assertEqual(0, len(model.tokens.token_log))

        save_token_ids = dict(model.tokens.token_ids)
        save_tokens = dict(model.tokens.tokens)

        model = Model(TEST_MODEL)

        self.assertEqual(save_token_ids, model.tokens.token_ids)
        self.assertEqual(save_tokens, model.tokens.tokens)

    def test_ngrams(self):
        model = Model(TEST_MODEL)
        tokens = "this is a test string for n-grams".split()

        # Test n=3
        ngrams = list(model._ngrams(tokens, 3))
        expected = [["this", "is", "a"],
                    ["is", "a", "test"],
                    ["a", "test", "string"],
                    ["test", "string", "for"],
                    ["string", "for", "n-grams"]]

        # Test n=2
        ngrams = list(model._ngrams(tokens, 2))
        expected = [["this", "is"],
                    ["is", "a"],
                    ["a", "test"],
                    ["test", "string"],
                    ["string", "for"],
                    ["for", "n-grams"]]

        # Test unigrams
        ngrams = list(model._ngrams(tokens, 1))
        expected = [["this"], ["is"], ["a"], ["test"], ["string"],
                    ["for"], ["n-grams"]]

        self.assertEquals(expected, ngrams)

    def test_ngrams_short(self):
        model = Model(TEST_MODEL)
        tokens = "this is".split()

        # Test n=3 with a string that doesn't have any 3-grams
        ngrams = list(model._ngrams(tokens, 3))
        expected = []

        self.assertEquals(expected, ngrams)

    def test_train(self):
        model = Model(TEST_MODEL)

        tokens = "<S> this is a test string </S>".split()
        model.train(tokens)

        counts = [(1, ("<S>", "this", "is")),
                  (1, ("test", "string", "</S>")),
                  (1, ("this", "is", "a")),
                  (1, ("is", "a", "test")),
                  (1, ("a", "test", "string")),
                  (0, ("will", "not", "find"))]

        # Make sure the model was saved
        self.assertEquals(0, len(model.counts_log))

        for count, ngram in counts:
            self.assertEquals(count, model.ngram_count(ngram))

        # Now train the phrase again and make sure the new counts were
        # merged.
        model.train(tokens)

        for count, ngram in counts:
            if count != 0:
                count += 1

            self.assertEquals(count, model.ngram_count(ngram))

    def test_train_many(self):
        model = Model(TEST_MODEL)

        sentences = ["this is a test",
                     "this is another test",
                     "this is a third test"]

        def tokens_gen(items):
            for sentence in items:
                yield sentence.split()

        model.train_many(tokens_gen(sentences))

        # Make sure the model was saved
        self.assertEquals(0, len(model.counts_log))

        self.assertEquals(2, model.ngram_count("this is a".split()))
        self.assertEquals(1, model.ngram_count("is a test".split()))
        self.assertEquals(1, model.ngram_count("this is another".split()))
        self.assertEquals(1, model.ngram_count("is a third".split()))

    def test_add_count(self):
        # Since _add_count adds to a LevelDB WriteBatch directly, and
        # the bindings for WriteBatch don't make it easy to figure out
        # what has been queued, test _add_count via its side effects
        # in the database.
        model = Model(TEST_MODEL)

        ngram = "one two three".split()
        self.assertEquals(0, model.ngram_count(ngram))

        model.train(ngram)
        self.assertEquals(1, model.ngram_count(ngram))

        # Ensure new counts are added to existing database counts
        model.train(ngram)
        self.assertEquals(2, model.ngram_count(ngram))

    def test_logprob_with_counts(self):
        # Make a couple of logprob checks with a model that tracks the
        # default trigrams, bigrams, and unigrams
        model = Model(TEST_MODEL)

        # Test before and after a save
        model.train("one two three".split())
        model.train("one two four".split())

        ngram = "one two three".split()
        token, context = ngram[-1], ngram[:-1]
        self.assertAlmostEqual(0.69314718, model.logprob(token, context))

    def test_prob_with_counts(self):
        # Make a couple of probability checks with a model that tracks
        # the default trigrams, bigrams, and unigrams
        model = Model(TEST_MODEL)

        # Test before and after a save
        model.train("one two three".split())
        model.train("one two four".split())

        ngram = "one two three".split()
        token, context = ngram[-1], ngram[:-1]
        self.assertAlmostEqual(0.5, model.prob(token, context))

    def test_autosave(self):
        model = Model(TEST_MODEL)
        self.assertEqual(0, len(model.counts_log))

        # force the autosave threshold down and make sure it fires
        # once enough counts have been logged
        model.SAVE_THRESHOLD = 5

        for num in xrange(model.SAVE_THRESHOLD):
            trigram = [str(num)] * 3

            model._train_tokens(trigram)
            model._autosave()

            self.assert_(len(model.counts_log) <= model.SAVE_THRESHOLD)

    def test_choose_random_word(self):
        model = Model(TEST_MODEL)

        # First, train one sentence and make sure we randomly pick the
        # only possible option.
        model.train("one two three".split())
        context = ["one", "two"]

        self.assertEqual("three", model.choose_random_word(context))

        # Train another sentence and make sure we pick both options
        # with carefully chosen seeding. Explicitly use Python's (old)
        # WichmannHill PRNG to ensure reproducability, since the
        # default PRNG generator could conceivably change in a future
        # release.
        model.train("one two four".split())

        rng = random.WichmannHill()

        rng.seed(0)
        self.assertEqual("three", model.choose_random_word(context, rng=rng))
        self.assertEqual("four", model.choose_random_word(context, rng=rng))

    def test_prefix_keys(self):
        # Fake some interesting keys and values to make sure the
        # prefix iterators are working
        model = Model(TEST_MODEL)

        model.kv.Put("a/", "a")
        model.kv.Put("a/b", "b")
        model.kv.Put("a/c", "c")
        model.kv.Put("a/d", "d")
        model.kv.Put("a/e", "e")
        model.kv.Put("a/f", "f")
        model.kv.Put("b/", "b")
        model.kv.Put("c/", "c")
        model.kv.Put("d/", "d")

        a_list = list(model._prefix_keys("a/"))
        self.assertEqual("a/ a/b a/c a/d a/e a/f".split(), a_list)

        a_list = list(model._prefix_keys("a/", skip_prefix=True))
        self.assertEqual(["", "b", "c", "d", "e", "f"], a_list)

        self.assertEqual(["b/"], list(model._prefix_keys("b/")))
        self.assertEqual(["c/"], list(model._prefix_keys("c/")))
        self.assertEqual(["d/"], list(model._prefix_keys("d/")))

    def test_prefix_items(self):
        # Fake some interesting keys and values to make sure the
        # prefix iterators are working
        model = Model(TEST_MODEL)

        model.kv.Put("a/", "a")
        model.kv.Put("a/b", "b")
        model.kv.Put("a/c", "c")
        model.kv.Put("a/d", "d")
        model.kv.Put("a/e", "e")
        model.kv.Put("a/f", "f")
        model.kv.Put("b/", "b")
        model.kv.Put("c/", "c")
        model.kv.Put("d/", "d")

        expected = [("a/", "a"),
                    ("a/b", "b"),
                    ("a/c", "c"),
                    ("a/d", "d"),
                    ("a/e", "e"),
                    ("a/f", "f")]

        a_list = list(model._prefix_items("a/"))
        self.assertEqual(expected, a_list)

        expected = [("", "a"),
                    ("b", "b"),
                    ("c", "c"),
                    ("d", "d"),
                    ("e", "e"),
                    ("f", "f")]

        a_list = list(model._prefix_items("a/", skip_prefix=True))
        self.assertEqual(expected, a_list)

if __name__ == '__main__':
    unittest.main()
