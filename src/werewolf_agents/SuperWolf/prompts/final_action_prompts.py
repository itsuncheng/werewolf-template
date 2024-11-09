def get_initial_action_prompt(role_prompt, game_situation, inner_monologue, action_type):
  return f"""{role_prompt}

Current game situation (including past thoughts and actions): 
{game_situation}

Your thoughts:
{inner_monologue}

Based on your thoughts and the current situation, what is your {action_type}? Respond with only the {action_type} and no other sentences/thoughts."""

def get_reflection_prompt(role_prompt, game_situation, inner_monologue, initial_action):
    return f"""{role_prompt}

Current game situation (including past thoughts and actions):
{game_situation}

Your thoughts:
{inner_monologue}

Your initial action:
{initial_action}

Reflect on your final action given the situation and provide any criticisms. Answer the following questions:
1. What is my name and my role? 
2. Does my action align with my role and am I revealing too much about myself in a public channel?
3. Does my action harm my team or my own interests?
4. How can I improve my action to better help my team and help me survive?"""