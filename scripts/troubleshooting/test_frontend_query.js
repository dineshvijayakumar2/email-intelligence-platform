#!/usr/bin/env node
/**
 * Test the exact query the frontend uses with Supabase JS client
 */
const { createClient } = require('@supabase/supabase-js');
require('dotenv').config({ path: '.env.local' });

const supabaseUrl = process.env.REACT_APP_SUPABASE_URL;
const supabaseKey = process.env.REACT_APP_SUPABASE_ANON_KEY;

console.log('Testing frontend Supabase query...');
console.log(`URL: ${supabaseUrl}\n`);

const supabase = createClient(supabaseUrl, supabaseKey);

async function testQuery() {
  try {
    // Exact same query as frontend
    const { data, error } = await supabase
      .from('email_categories')
      .select('category')
      .not('category', 'is', null)
      .not('category', 'like', '_meta_%');

    if (error) {
      console.error('Query error:', error);
      return;
    }

    console.log(`Total rows returned: ${data.length}`);

    // Get unique categories
    const categorySet = new Set(data.map(item => item.category).filter(Boolean));
    const categories = Array.from(categorySet).sort();

    console.log(`\nUnique categories: ${categories.length}`);
    console.log('\nCategories:');
    categories.forEach(cat => console.log(`  - ${cat}`));

  } catch (err) {
    console.error('Error:', err);
  }
}

testQuery();
